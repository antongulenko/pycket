
from pycket.cont import label
from pycket.values import W_MVector, W_Object, W_Fixnum, W_Flonum, W_Null, UNROLLING_CUTOFF
from rpython.rlib.objectmodel import import_from_mixin
from rpython.rlib import jit
from pycket import rstrategies as rstrat

class AbstractStrategy(object):
    __metaclass__ = rstrat.StrategyMetaclass
    import_from_mixin(rstrat.AbstractCollection)
    import_from_mixin(rstrat.AbstractStrategy)
    import_from_mixin(rstrat.SafeIndexingMixin)
    _attrs_ = ["w_self"]
    
    def strategy_factory(self):
        return _factory
    def __init__(self, size):
        self.w_self = None
        self.init_strategy(size)
    def __str__(self):
        return "%s(size %i)" % (self.__class__.__name__, self.size())

@rstrat.strategy()
class ObjectVectorStrategy(AbstractStrategy):
    import_from_mixin(rstrat.GenericStrategy)
    def default_value(self): return W_Null()

@rstrat.strategy(generalize=[ObjectVectorStrategy])
class FlonumVectorStrategy(AbstractStrategy):
    import_from_mixin(rstrat.SingleTypeStrategy)
    contained_type = W_Flonum
    def default_value(self): return W_Flonum(0)
    def wrap(self, val): return W_Flonum(val)
    def unwrap(self, w_val):
        assert isinstance(w_val, W_Flonum)
        return w_val.value

@rstrat.strategy(generalize=[ObjectVectorStrategy])
class FixnumVectorStrategy(AbstractStrategy):
    import_from_mixin(rstrat.SingleTypeStrategy)
    contained_type = W_Fixnum
    def default_value(self): return W_Fixnum(0)
    def wrap(self, val):
        # TODO what primitive datatype is represented by Fixnum?
        assert isinstance(val, int)
        return W_Fixnum(val)
    def unwrap(self, w_val):
        assert isinstance(w_val, W_Fixnum)
        return w_val.value

class StrategyFactory(rstrat.StrategyFactory):
    _immutable_fields_ = ["no_specialized[*]?"]
    
    def __init__(self):
        super(StrategyFactory, self).__init__(AbstractStrategy)
        self.no_specialized = [True]
    
    def strategy_for_elems(self, elems):
        if self.no_specialized[0]:
            strategy_type = ObjectVectorStrategy
        else:
            strategy_type = self.strategy_type_for(elems)
        return strategy_type(len(elems))
        
    def strategy_for_elem(self, elem, times):
        if self.no_specialized[0] or times == 0:
            strategy_type = ObjectVectorStrategy
        else:
            strategy_type = self.strategy_type_for([elem])
        return strategy_type(times)
    
    def instantiate_and_switch(self, old_strategy, size, new_strategy_type):
        new_strategy = new_strategy_type(size)
        w_self = old_strategy.w_self
        w_self.strategy = new_strategy
        new_strategy.w_self = w_self
        return new_strategy
    
    def instantiate_empty(self, strategy_type):
        return strategy_type(0)

_factory = StrategyFactory()

class W_Vector(W_MVector):
    _immutable_fields_ = ["strategy?"]
    errorname = "vector"
    
    def __init__(self, strategy):
        strategy.w_self = self
        self.strategy = strategy
    
    @staticmethod
    def fromelements(elems):
        s = _factory.strategy_for_elems(elems)
        for i, elem in enumerate(elems):
            s.store(i, elem)
        instance = W_Vector(s)
        _factory.log(s)
        return instance
    
    @staticmethod
    def fromelement(elem, times):
        s = _factory.strategy_for_elem(elem, times)
        for i in range(times):
            s.store(i, elem)
        instance = W_Vector(s)
        _factory.log(s)
        return instance
    
    def ref(self, i):
        return self.strategy.fetch(i)
    def set(self, i, v):
        self.strategy.store(i, v)
    # unsafe versions
    # TODO add unsafe versions
    def _ref(self, i):
        return self.ref(i)
    def _set(self, i, v):
        return self.set(i, v)
    
    @label
    def vector_set(self, i, new, env, cont):
        from pycket.interpreter import return_value
        from pycket.values import w_void
        self.set(i.value, new)
        return return_value(w_void, env, cont)

    @label
    def vector_ref(self, i, env, cont):
        from pycket.interpreter import return_value
        return return_value(self.ref(i.value), env, cont)

    @jit.look_inside_iff(
        lambda strategy, w_vector: jit.isconstant(w_vector.length()) and
               w_vector.length() < UNROLLING_CUTOFF)
    def ref_all(self, w_vector):
        return [self.ref(i) for i in range(self.length())]

    def length(self):
        return self.strategy.size()
    def tostring(self):
        l = self.ref_all(self)
        return "#(%s)" % " ".join([obj.tostring() for obj in l])

    def equal(self, other):
        # XXX could be optimized using strategies
        if not isinstance(other, W_MVector):
            return False
        if self is other:
            return True
        if self.length() != other.length():
            return False
        for i in range(self.length()):
            if not self.ref(i).equal(other.ref(i)):
                return False
        return True

