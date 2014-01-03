
from pycket.values import W_Object

class W_List(W_Object):
    errorname = "list"
    def __init__(self):
        raise NotImplementedError("abstract base class")

class W_Cons(W_List):
    errorname = "pair"
    def __init__(self, a, d):
        self.car = a
        self.cdr = d
    def tostring(self):
        return "(%s . %s)"%(self.car.tostring(), self.cdr.tostring())

class W_Null(W_List):
    def __init__(self): pass
    def tostring(self): return "()"

w_null = W_Null()

def to_list(l): return to_improper(l, w_null)

def to_improper(l, v):
    if not l:
        return v
    else:
        return W_Cons(l[0], to_improper(l[1:], v))
