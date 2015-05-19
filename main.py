import json
from os.path import join


base64_line = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
base64_map = {c: i for i, c in enumerate(base64_line)}


def parse_vlq64(v):
    result = []
    vbytes = []
    for ch in v:
        b = base64_map[ch]
        vbytes.append(b & 0x1F)
        if not (b & 0x20):
            vbytes.reverse()
            value = 0
            for x in vbytes:
                value = (value << 5) | x
            sgn = value & 0x1
            value >>= 1
            if sgn:
                value = -value
            result.append(value)
            vbytes = []
    if vbytes:
        raise Exception('VLQ number not finished')
    return result


def dump_vlq64(values):
    result = []
    for value in values:
        sgn = 0 if value >= 0 else 1
        if sgn:
            value = -value
        value = (value << 1) | sgn
        vbytes = []
        while value:
            vbytes.append((value & 0x1F) | 0x20)
            value >>= 5
        if not vbytes:
            vbytes = [0]
        vbytes[-1] &= 0x1F
        result.append(''.join(base64_line[ch] for ch in vbytes))
    return ''.join(result)


class SourceMapParsingException(Exception):
    pass


class SourceMap:
    def __init__(self):
        self.file = None
        self.sourceRoot = None
        self.sources = []
        self.names = []
        self.lines = []

    def lookup(self, line, column, useSourceRoot=True):
        if column < 0:
            raise ValueError('Column can not be negative')
        seglist = self.lines[line]
        a, b = 0, len(seglist)
        seg = None
        while b - a > 0:
            c = (a + b) // 2
            if seglist[c][0] <= column and (c >= len(seglist) - 1 or column < seglist[c + 1][0]):
                seg = seglist[c]
                break
            elif column < seglist[c][0]:
                b = c
            else:
                a = c + 1
        if seg is None:
            raise IndexError('Segment not found')
        if len(seg) == 1:
            return None
        result = {
            'source': self.sources[seg[1]],
            'line': seg[2],
            'column': seg[3],
        }
        if useSourceRoot:
            result['source'] = join(self.sourceRoot, result['source'])
        if len(seg) > 4:
            result['name'] = seg[4]
        return result

    def dump(self, serialize=True):
        mappings = []
        prevsource, prevsourceline, prevsourcecolumn, prevname = 0, 0, 0, 0
        for line in self.lines:
            resultline = []
            prevcolumn = 0
            for seg in line:
                st = [seg[0] - prevcolumn]
                prevcolumn = seg[0]
                if len(seg) > 1:
                    st.append(seg[1] - prevsource)
                    st.append(seg[2] - prevsourceline)
                    st.append(seg[3] - prevsourcecolumn)
                    prevsource, prevsourceline, prevsourcecolumn = seg[1:4]
                if len(seg) > 4:
                    st.append(seg[4] - prevname)
                    prevname = seg[4]
                resultline.append(dump_vlq64(st))
            mappings.append(','.join(resultline))
        mapdata = {
            'version': 3,
            'file': self.file,
            'sourceRoot': self.sourceRoot,
            'sources': self.sources.copy(),
            'names': self.names.copy(),
            'mappings': ';'.join(mappings),
        }
        if serialize:
            return json.dumps(mapdata)
        return mapdata


def create_from_json(jsondata):
    self = SourceMap()
    if not isinstance(jsondata, dict):
        jsondata = json.loads(jsondata)
    if jsondata.get('version') != 3:
        raise SourceMapParsingException('Bad sourcemap version')
    # TODO: move to json schema
    for k in ('file', 'sourceRoot'):
        v = jsondata.get(k, '')
        if not isinstance(v, str):
            raise SourceMapParsingException('Parameter {} must be string'.format(k))
        setattr(self, k, v)
    for k in ('sources', 'names'):
        v = jsondata.get(k, [])
        if not isinstance(v, list):
            raise SourceMapParsingException('Parameter {} must be array'.format(k))
        setattr(self, k, v)
    
    self.lines = []
    column, source, sourceline, sourcecolumn, name = 0, 0, 0, 0, 0
    for group in jsondata['mappings'].split(';'):
        if group == '':
            self.lines.append([])
            continue
        column = 0
        linegroup = []
        for seg in group.split(','):
            segp = parse_vlq64(seg)

            column += segp[0]
            if len(segp) >= 4:
                source += segp[1]
                sourceline += segp[2]
                sourcecolumn += segp[3]
            if len(segp) == 5:
                name += segp[4]

            if len(segp) == 1:
                x = (column,)
            elif len(segp) == 4:
                x = (column, source, sourceline, sourcecolumn)
            elif len(segp) == 5:
                x = (column, source, sourceline, sourcecolumn, name)
            else:
                raise Exception('Invalid segment {}'.format(segp))

            linegroup.append(x)
        self.lines.append(linegroup)
    return self


def cascade_sourcemaps(mapunder, mapover):
    result = SourceMap()

    # TODO: merge paths!
    #result.sourceRoot = mapunder.sourceRoot
    # TODO: names!

    result.file = mapover.file
    result.sources = mapunder.sources.copy()

    sourceindex = {v: i for i, v in enumerate(result.sources)}

    for line in mapover.lines:
        resultline = []
        for seg in line:
            if len(seg) == 2:
                resultline.append(seg)
            else:
                lk = mapunder.lookup(seg[2], seg[3], useSourceRoot=False)
                resultline.append((
                    seg[0], # starting column
                    sourceindex[lk['source']], # source file
                    lk['line'], # line in source
                    lk['column'], # column in source
                ))
        result.lines.append(resultline)
    return result


def concat_sourcemaps(*items):
    '''You can pass as item:
    - SourceMap instance
    - list of lines of lexeme lengths (identity map): (sourceFileName, [[lexemelen, lexemelen, ...], [lexemelen, lexemelen, ...], ...])
    - integer count of not mapped lines (for example, you can make wrappers or comments in resulting file)
    '''
    result = SourceMap()
    smap = {}
    for item in items:
        if isinstance(item, int):
            for i in range(item):
                result.lines.append([])
        elif isinstance(item, SourceMap):
            local_smap = {}
            for i, source in enumerate(item.sources):
                # TODO: join paths
                if source not in smap:
                    smap[source] = len(result.sources)
                    result.sources.append(source)
                local_smap[i] = smap[source]
            for line in item.lines:
                rline = []
                for seg in line:
                    if len(seg) == 1:
                        rline.append(seg)
                    else:
                        # TODO: names
                        rline.append((seg[0], local_smap[seg[1]], seg[2], seg[3]))
                result.lines.append(rline)
        else:
            # TODO: paths
            sname = item[0]
            if sname not in smap:
                smap[sname] = len(result.sources)
                result.sources.append(sname)
            sidx = smap[sname]
            for line in item[1]:
                rline = []
                column = 0
                for i, lexlen in enumerate(line):
                    rline.append((column, sidx, i, column))
                    column += lexlen
                result.lines.append(rline)
    return result


def print_near(fname, line, col):
    with open(fname) as f:
        lines = f.readlines()
    width = 80
    from_, to_ = col - width // 2, col + width // 2
    if from_ < 0:
        from_, to_ = 0, width
    for i in range(max(0, line - 3), line + 3):
        l = lines[i].rstrip('\n\r')
        if i != line:
            print(l[from_:to_])
        else:
            print('{}\x1B[7;91m{}\x1B[27;39m{}'.format(l[from_:col], l[col], l[col+1:to_]))


if __name__ == '__main__':
    with open('../webgl/build/camera.js.map') as f:
        contents = f.read()
    jdict = json.loads(contents)
    smap = create_from_json(jdict)
    p = (1, 11)
    lk = smap.lookup(*p)
    print(lk)
    print_near('../webgl/build/camera.js', *p)
    print('===========')
    print_near('../webgl/camera.coffee', lk['line'], lk['column'])
    jd2 = smap.dump(serialize=False)

    print(jdict == jd2)
    #print(jdict)
    #print(jd2)
