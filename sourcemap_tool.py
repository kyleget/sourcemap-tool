import argparse
from sourcemap_lib import discover_sourcemap, create_from_json, concat_sourcemaps, cascade_sourcemaps
from os.path import join, dirname, normpath, isabs
from sys import exit, stderr

# TODO: support different encodings and line endings


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


def filepath_relative_to_file(basefile, relpath):
    if isabs(relpath):
        return relpath
    return normpath(join(dirname(basefile), relpath))


def lookup(args):
    if args.mapfile:
        mapname = args.mapfile
    else:
        mapname = filepath_relative_to_file(args.file.name, discover_sourcemap(args.file))
    with open(mapname, 'r') as mapfile:
        mp = create_from_json(mapfile.read())
    try:
        lk = mp.lookup(args.line, args.column)
    except IndexError:
        exit(1)  # if position not found
    sourcename = filepath_relative_to_file(mapname, lk['source'])
    if not args.showcode:
        print('{} {} {}'.format(sourcename, lk['line'], lk['column']))
    else:
        print_near(sourcename, lk['line'], lk['column'])


def lex(code_lines, lexername):
    try:
        from pygments.lexers import get_lexer_by_name
        from pygments import lex
    except ImportError:
        print('For lexer support please install extras: pip install sourcemap-tool[lexer]', file=stderr)
        exit(1)

    # TODO: join lexemes with trailing space, remove comment lexemes
    lexer = get_lexer_by_name(lexername)
    tokens = lex(''.join(code_lines), lexer)
    result = []
    line = []
    for _, text in tokens:
        parts = text.split('\n')
        if len(parts) > 1: # multiline token
            first = True
            for part in parts:
                if not first:
                    result.append(line)
                    line = []
                first = False
                if len(part) > 0:
                    line.append(len(part))
        else:
            if len(text) > 0:
                line.append(len(text))
    if line:
        result.append(line)
    return result


def concat(args):
    result_code = []
    smaplist = []
    for fconfig in args.file:
        code_lines = fconfig['file'].readlines()
        try:
            mapurl, markerline = discover_sourcemap(code_lines, return_line_number=True)
            code_lines.pop(markerline)
        except IndexError:
            mapurl, markerline = None, None
        mappath = None
        if 'map' in fconfig:
            mappath = fconfig['map']
        else:
            if mapurl is not None:
                mappath = filepath_relative_to_file(fconfig['file'].name, mapurl)
        lexer = fconfig.get('lexer', None)
        if mappath is not None:
            with open(mappath, 'r') as f:
                smap = create_from_json(f.read())
            if markerline:
                try:
                    smap.lines.pop(markerline)
                except IndexError:
                    pass
        elif lexer is not None:
            smap = (fconfig['file'].name, lex(code_lines, lexer))
        else:
            smap = len(code_lines)
        result_code.extend(code_lines)
        smaplist.append(smap)
    mergedmap = concat_sourcemaps(*smaplist)
    args.outmap.write(mergedmap.dump())
    args.outfile.writelines(result_code)


def cascade(args):
    mapunder = create_from_json(args.mapunder.read())
    mapover = create_from_json(args.mapover.read())
    resultmap = cascade_sourcemaps(mapunder, mapover)
    args.outmap.write(resultmap.dump())


def non_negative_int(line):
    val = int(line)
    if val < 0:
        raise argparse.ArgumentTypeError('{} is negative'.format(val))
    return val


class FileConcatList(argparse.Action):
    def __call__(self, parser, namespace, value, option_string):
        lst = getattr(namespace, 'file')
        if lst is None:
            lst = []
        if self.dest == 'file':
            lst.append({'file': value})
        elif self.dest == 'map':
            if lst: # silently ignore maps and lexers without file
                lst[-1]['map'] = value
        elif self.dest == 'lexer':
            if lst:
                lst[-1]['lexer'] = value
        setattr(namespace, 'file', lst)


def create_parser():
    parser = argparse.ArgumentParser(description='Swiss knife for sourcemaps')
    subparsers = parser.add_subparsers(dest='tool', title='available tools')
    subparsers.required=True

    parser_lookup = subparsers.add_parser('lookup', help='Perform sourcemap lookup', description='For given position in compiled file find position in source')
    parser_lookup.add_argument('file', type=argparse.FileType('r'), help='Compiled file used for lookup')
    parser_lookup.add_argument('line', type=non_negative_int, help='Line number (counting from zero)')
    parser_lookup.add_argument('column', type=non_negative_int, help='Column number, character position in line (counting from zero)')
    # TODO: rename to map
    parser_lookup.add_argument('--mapfile', type=argparse.FileType('r'), help='Directly assign sourcemap file')
    parser_lookup.add_argument('--showcode', action='store_true', help='Output vicinal code from source file')
    parser_lookup.set_defaults(func=lookup)

    parser_concat = subparsers.add_parser('concat', help='Concatenate sourcemaps and scripts')
    group = parser_concat.add_argument_group('files for concatenation', 'Use multiple series of these arguments starting with --file')
    group.add_argument('--file', type=argparse.FileType('r'), action=FileConcatList, required=True, help='Files for concatenation. Can have or have no sourcemap, can even be any raw code')
    group.add_argument('--map', type=argparse.FileType('r'), action=FileConcatList, help='Directly assign sourcemap')
    group.add_argument('--lexer', action=FileConcatList, help='Use certain pygments lexer for file without sourcemap')
    group = parser_concat.add_argument_group('output')
    group.add_argument('--outfile', type=argparse.FileType('w'), required=True, help='Output path for concatenated code')
    group.add_argument('--outmap', type=argparse.FileType('w'), required=True, help='Output path for concatenated sourcemap')
    parser_concat.set_defaults(func=concat)

    parser_cascade = subparsers.add_parser('cascade', help='Merge multiple stage sourcemaps')
    parser_cascade.add_argument('mapunder', type=argparse.FileType('r'), help='Underlying map (previous step)')
    parser_cascade.add_argument('mapover', type=argparse.FileType('r'), help='Overlying map (next step applied on top of result of previous)')
    parser_cascade.add_argument('outmap', type=argparse.FileType('w'), help='Output path for resulting combined sourcemap')
    parser_cascade.set_defaults(func=cascade)
    return parser

if __name__ == '__main__':
    args = create_parser().parse_args()
    args.func(args)
