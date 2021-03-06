def test_hash_simple(doctest):
    """
    ! (define ht (make-hash))
    ! (hash-set! ht "apple" '(red round))
    ! (hash-set! ht "banana" '(yellow long))
    > (hash-ref ht "apple")
    '(red round)
    E (hash-ref ht "coconut")
    > (hash-ref ht "coconut" "not there")
    "not there"
    > (hash-count ht)
    2
    """

def test_hasheqv(doctest):
    """
    ! (define ht (make-hasheqv))
    > (hash-set! ht 1.0 'a)
    > (hash-set! ht 2.0 'a)
    > (hash-ref ht (+ 1.0 1.0))
    'a
    """

def test_hash_symbols(doctest):
    """
    ! (define ht (make-hash))
    ! (hash-set! ht 'a '(red round))
    ! (hash-set! ht 'b '(yellow long))
    > (hash-ref ht 'a)
    '(red round)
    > (hash-ref ht 'b)
    '(yellow long)
    E (hash-ref ht 'c)
    > (hash-ref ht 'c "not there")
    "not there"

    > (hash-set! ht 1 'ohnoes) ; dehomogenize
    > (hash-ref ht 'a)
    '(red round)
    > (hash-ref ht 'b)
    '(yellow long)
    > (hash-ref ht 1)
    'ohnoes
    """

def test_hash_strings(doctest):
    """
    ! (define ht (make-hash))
    ! (hash-set! ht "a" '(red round))
    ! (hash-set! ht "b" '(yellow long))
    > (hash-ref ht "a")
    '(red round)
    > (hash-ref ht "b")
    '(yellow long)
    E (hash-ref ht "c")
    > (hash-ref ht "c" "not there")
    "not there"

    > (hash-set! ht 1 'ohnoes) ; dehomogenize
    > (hash-ref ht "a")
    '(red round)
    > (hash-ref ht "b")
    '(yellow long)
    > (hash-ref ht 1)
    'ohnoes
    """


def test_hash_bytes(doctest):
    """
    ! (define ht (make-hash))
    ! (hash-set! ht #"a" '(red round))
    ! (hash-set! ht #"bc" '(yellow long))
    > (hash-ref ht #"a")
    '(red round)
    > (hash-ref ht #"bc")
    '(yellow long)
    > (hash-ref ht (bytes-append #"b" #"c"))
    '(yellow long)
    E (hash-ref ht #"c")
    > (hash-ref ht #"c" "not there")
    "not there"

    > (hash-set! ht 1 'ohnoes) ; dehomogenize
    > (hash-ref ht #"a")
    '(red round)
    > (hash-ref ht #"bc")
    '(yellow long)
    > (hash-ref ht 1)
    'ohnoes
    """


def test_hash_ints(doctest):
    """
    ! (define ht (make-hash))
    ! (hash-set! ht 1 '(red round))
    ! (hash-set! ht 1099 '(yellow long))
    > (hash-ref ht 1)
    '(red round)
    > (hash-ref ht 1099)
    '(yellow long)
    E (hash-ref ht 28)
    > (hash-ref ht 28 "not there")
    "not there"
    > (hash-ref ht 'foo 'nope)
    'nope
    > (hash-ref ht 1)
    '(red round)
    > (hash-ref ht 1099)
    '(yellow long)
    """

def test_hash_for_each(doctest):
    """
    ! (define x 1)
    ! (define h #hash((1 . 2) (2 . 3) (3 . 4)))
    ! (define (fe c v) (set! x (+ x (* c v))))
    ! (hash-for-each h fe)
    > x
    21
    """

def test_hash_map(doctest):
    """
    ! (define h #hash((1 . 2) (2 . 3) (3 . 4)))
    ! (define s (hash-map h (lambda (k v) (+ k v))))
    > s
    > (or (equal? s '(3 5 7)) (equal? s '(3 7 5))
          (equal? s '(5 3 7)) (equal? s '(5 7 3))
          (equal? s '(7 3 5)) (equal? s '(7 5 3)))
    #t
    """

def test_use_equal(doctest):
    """
    ! (define ht (make-hash))
    ! (define key (cons 'a 'b))
    ! (hash-set! ht key 1)
    ! (define hteqv (make-hasheqv))
    ! (hash-set! hteqv key 1)
    > (hash-ref ht key)
    1
    > (hash-ref ht (cons 'a 'b) 2)
    1
    ; now with eqv
    > (hash-ref hteqv key)
    1
    > (hash-ref hteqv (cons 'a 'b) 2)
    2
    """

def test_hash_tableau(doctest):
    """
    ! (define ht #hash((1.0 . 3) (1 . 2)))
    ! (define ht2 '#hash(((a . b) . 1)))
    > (hash-ref ht 1.0)
    3
    > (hash-ref ht 1)
    2
    > (hash-ref ht2 (cons 'a 'b) 2)
    1
    """

def test_default_hash(source):
    """
    (let ()
    (make-weak-hasheq)
    (make-immutable-hash)
    (make-hash)
    (make-hasheq)
    (make-hasheqv)
    #t)
    """
    from pycket.test.testhelper import run_mod_expr
    from pycket.values import w_true
    result = run_mod_expr(source, wrap=True)
    assert result is w_true

def test_get_item():
    from rpython.rtyper.test.test_llinterp import interpret, get_interpreter
    from pycket.values_hash import get_dict_item
    def tg(a, b, c, d):
        dct = {str(a): b, str(c): d}
        i = 0
        while 1:
            print i
            try:
                x, y = get_dict_item(dct, i)
                print x, y
                assert (x == str(a) and y == b) or (x == str(c) and y == d)
            except KeyError:
                pass
            except IndexError:
                break
            i += 1
    tg("1", 2, "3", 4)
    interpret(tg, [1, 2, 334, 4])
