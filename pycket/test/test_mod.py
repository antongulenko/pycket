import pytest
from pycket.expand import expand, to_ast, parse_module, expand_string
from pycket.interpreter import *
from pycket.values import *
from pycket.prims import *

from pycket.test.testhelper import run, run_fix, run_mod_expr, run_mod_defs, run_mod

def test_empty_mod():
    run_mod_defs("")

def test_racket_mod():
    m = run_mod("#lang racket/base\n (define x 1)")
    ov = m.defs[W_Symbol.make("x")]
    assert ov.value == 1

def test_constant_mod():
    run_mod_expr("1")

def test_constant_mod_val():
    ov = run_mod_expr("1")
    assert isinstance(ov, W_Fixnum)
    assert ov.value == 1

# look ma, no modules!
def test_constant():
    run_fix("1", v=1)

def test_set_modvar():
    m = run_mod("""
#lang pycket

(define sum 0)

(define (tail-rec-aux i n)
  (if (< i n)
      (begin (set! sum (+ sum 1)) (tail-rec-aux (+ i 1) n))
      sum))

(tail-rec-aux 0 100)
""")
    ov = m.defs[W_Symbol.make("sum")].get_val()
    assert ov.value == 100

def test_set_mod2():
    m = run_mod("""
#lang pycket
(provide table)
(define table #f)
(set! table #f)
""")
    ov = m.defs[W_Symbol.make("table")]
    assert isinstance(ov, W_Cell)


def test_set_mod_other():
    m = run_mod("""
#lang pycket
    (require pycket/set-export)
(define y (not x))
""")
    assert m.defs[W_Symbol.make("y")]

def test_use_before_definition():
    with pytest.raises(SchemeException):
        m = run_mod("""
        #lang pycket
        x
        (define x 1)
    """)

    with pytest.raises(SchemeException):
        m = run_mod("""
        #lang pycket
        x
        (define x 1)
        (set! x 2)
    """)

def test_shadowing_macro():
    m = run_mod("""
#lang pycket

(define-syntax bind+
  (syntax-rules ()
    [(bind+ v e) (let ([x v]) (+ x e))]
    [(bind+ v0 v ... e) (let ([x v0]) (bind+ v ... (+ x e)))]))

(define x (bind+ 1 2 3))
""")
    ov = m.defs[W_Symbol.make("x")]
    assert ov.value == 6
