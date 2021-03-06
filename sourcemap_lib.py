import json
from os.path import join, normpath, isabs

# TODO: use urldecode/urlencode for urls


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


class SourceMapParsingException(ValueError):
    pass


class SegmentNotFoundException(IndexError):
    pass


def url_to_path(u):
    # TODO: support for absolute urls, cut off their schemes?
    return join(*u.split('/'))


def safe_join(a, b):
    if isabs(b):
        return b
    return normpath(join(a, b))


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
            raise SegmentNotFoundException
        if len(seg) == 1:
            # return None # segment without any link
            raise SegmentNotFoundException
        result = {
            'source': self.sources[seg[1]],
            'line': seg[2],
            'column': seg[3],
        }
        if useSourceRoot:
            result['source'] = safe_join(self.sourceRoot, result['source'])
        if len(seg) > 4:
            result['name'] = seg[4]
        return result

    def dump(self, serialize=True):
        # TODO: cleanup unused references
        # TODO: cleanup zero-len segments
        # TODO: merge same target segments
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
            'file': '' if self.file is None else self.file,
            'sourceRoot': '' if self.sourceRoot is None else self.sourceRoot,
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
        if k == 'sourceRoot':
            v = url_to_path(v)
        setattr(self, k, v)
    for k in ('sources', 'names'):
        v = jsondata.get(k, [])
        if not isinstance(v, list):
            raise SourceMapParsingException('Parameter {} must be array'.format(k))
        for vv in v:
            if not isinstance(vv, str):
                raise SourceMapParsingException('Array element {} inside {} must be string'.format(vv, k))
        if k == 'sources':
            v = [url_to_path(vv) for vv in v]
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
    '''
    sourceRoot for each SourceMap instance required to be normalized absolute file path.
    source for each SourceMap can be relative to sourceRoot or absolute file path.
    '''
    result = SourceMap()

    # TODO: names!

    result.file = mapover.file
    result.sourceRoot = ''
    result.sources = [safe_join(mapunder.sourceRoot, v) for v in mapunder.sources]

    sourceindex = {v: i for i, v in enumerate(result.sources)}

    for line in mapover.lines:
        resultline = []
        for seg in line:
            if len(seg) == 2:
                resultline.append(seg)
            else:
                try:
                    lk = mapunder.lookup(seg[2], seg[3], useSourceRoot=True)
                    resultline.append((
                        seg[0],  # starting column
                        sourceindex[lk['source']],  # source file
                        lk['line'],  # line in source
                        lk['column'],  # column in source
                    ))
                except SegmentNotFoundException:
                    resultline.append((seg[0],))
                except IndexError:
                    resultline.append((seg[0],))
        result.lines.append(resultline)
    return result


def concat_sourcemaps(*items):
    '''You can pass as item:
    - SourceMap instance
    - list of lines of lexeme lengths (identity map): (sourceFileName, [[lexemelen, lexemelen, ...], [lexemelen, lexemelen, ...], ...])
    - integer count of not mapped lines (for example, you can make wrappers or comments in resulting file)

    sourceRoot for each SourceMap instance required to be normalized absolute file path.
    source for each SourceMap can be relative to sourceRoot or absolute file path.

    sourceFileName for each list of lines required to be normalized absolute file path.
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
                source = safe_join(item.sourceRoot, source)
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


def discover_sourcemap(file, return_line_number=False):
    # TODO: split method to find_marker, parse_marker, set_marker
    if isinstance(file, list):
        lines = file
    else:
        lines = file.readlines()
    lnum = len(lines) - 5 - 1
    for line in lines[-5:]:
        lnum += 1
        line = line.lstrip()
        if not (line.startswith('//@') or line.startswith('//#') or line.startswith('/*#')):
            continue
        line = line[3:].lstrip()
        if not line.startswith('sourceMappingURL='):
            continue
        _, url = line.split('=', 1)
        url, _ = (url.strip() + ' ').split(' ', 1)
        url = url.strip()
        if return_line_number:
            return (url, lnum)
        return url
    raise IndexError('Couldn\'t find sourceMappingURL in file')
