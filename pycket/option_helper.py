#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
import os

from .expand import (expand_file_to_json, expand_code_to_json,
                     ensure_json_ast_eval, ensure_json_ast_run,
                     PermException, SchemeException)

from rpython.rlib import jit


def script_exprs(arg, content):
    if False: pass
    elif arg in ["f", "r"]:
        exprs = '(load "%s")' % content
    elif arg in ["t", "u"]:
        exprs = '(require (file "%s"))' % content
    elif arg == "l":
        exprs = '(require (lib "%s"))' % content
    elif arg == "p":
        exprs = '(require (planet "%s"))' % content
    else:
        exprs = content
    return exprs

# Re-enable when we have a top-level
#   -f <file>, --load <file> : Like -e '(load "<file>")'
#   -r <file>, --script <file> : Same as -f <file> -N <file> -
#  --mcons: Support mutable conses

def print_help(argv):
    print """Welcome to Pycket.
%s [<option> ...] <argument> ...
 File and expression options:
  -e <exprs>, --eval <exprs> : Evaluate <exprs>, prints results
  -t <file>, --require <file> : Like -e '(require (file "<file>"))'
  -l <path>, --lib <path> : Like -e '(require (lib "<path>"))'
  -p <package> : Like -e '(require (planet "<package>")'
  -u <file>, --require-script <file> : Same as -t <file> -N <file> --
 Configuration options:
  --stdlib: Use Pycket's version of stdlib (only applicable for -e)
 Meta options:
  --jit <jitargs> : Set RPython JIT options may be 'default', 'off',
                    or 'param=value,param=value' list
  -- : No argument following this switch is used as a switch
  -h, --help : Show this information and exits, ignoring other options
Default options:
 If only an argument is specified, it is loaded and evaluated
""" % (argv[0])

_run = True
_eval = False
def parse_args(argv):
    config = {
        'stdlib': False,
#        'mcons': False,
        'mode': _run,
    }
    names = {
        # 'file': "",
        # 'exprs': "",
    }
    args = []
    retval = -1
    i = 1
    to = len(argv)
    while i < to:
        if False: pass
        elif argv[i] == "--jit":
            if to <= i + 1:
                print "missing argument after --jit"
                retval = 2
                break
            i += 1
            jitarg = argv[i]
            jit.set_user_param(None, jitarg)
        elif argv[i] in ["-h", "--help", "/?", "-?", "/h", "/help"]:
            print_help(argv)
            return (None, None, None, 0)
        elif argv[i] == "--":
            i += 1
            break
        elif argv[i] == "--stdlib":
            config['stdlib'] = True
            i += 1
        elif argv[i] == "-e":
            if to <= i + 1:
                print "missing argument after -e"
                retval = 5
                break
            retval = 0
            config['mode'] = _eval
            i += 1
            names['exprs'] = argv[i]
        elif argv[i] in ["-u", "-t", "-l", "-p"]:
            arg = argv[i][1]
            stop = arg in ["u"]

            if to <= i + 1:
                print "missing argument after -%s" % arg
                retval = 5
                break
            # if arg == "r":
            #     suffix = "f"
            elif arg == "u":
                suffix = "t"
            else:
                suffix = arg
            i += 1
            names['file'] = "%s.%s" % (argv[i], suffix)
            names['exprs'] = script_exprs(arg, argv[i])
            config['mode'] = _eval
            retval = 0
            if stop:
                i += 1
                break
        else:
            if 'file' in names:
                break
            names['file'] = argv[i]
            retval = 0
        i += 1

    if config['stdlib'] and (config['mode'] is not _eval):
        retval = -1

    if retval == -1:
        print_help(argv)
        retval = 3

    if i <= to: #pending args
        args = argv[i:to]

    return config, names, args, retval

def _temporary_file():
    from rpython.rlib.objectmodel import we_are_translated
    if we_are_translated():
        return os.tmpnam()
    else:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return os.tmpnam()

def ensure_json_ast(config, names):
    stdlib = config.get('stdlib', False)
    # mcons = config.get('mcons', False)
    # assert not mcons

    if config["mode"] is _eval:
        code = names['exprs']
        if 'file' in names:
            file_name = names['file']
        else:
            file_name = _temporary_file()
        assert not file_name.endswith('.json')
        json_file = ensure_json_ast_eval(code, file_name, stdlib)
    elif config["mode"] is _run:
        assert not stdlib
        assert 'file' in names
        file_name = names['file']
        if file_name.endswith('.json'):
            json_file = file_name
        else:
            try:
                json_file = ensure_json_ast_run(file_name)
            except PermException:
                json_file = None
    else:
        raise SchemeException("unknown mode %s" % config["mode"])
    return os.path.abspath(file_name), json_file

# EOF
