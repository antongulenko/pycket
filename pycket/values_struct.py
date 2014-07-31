from collections import namedtuple
from pycket import values
from pycket.cont import continuation, label
from pycket.error import SchemeException
from pycket.exposeprim import make_call_method
from pycket.small_list import inline_small_list
from pycket.values import from_list, w_void, w_null, w_false, w_true, W_Object, W_Fixnum, W_Symbol, W_Procedure, W_Prim
from rpython.rlib import jit

#
# Structs are partially supported
# 
# Not implemented:
# 1) prefab: need update in expand.rkt
# 2) methods overriding (including equal)

# TODO: inspector currently does nothing
class W_StructInspector(W_Object):
    errorname = "struct-inspector"
    _immutable_fields_ = ["super"]

    @staticmethod 
    def make(inspector, issibling = False):
        super = inspector
        if issibling:
            super = inspector.super if inspector is not None else None
        return W_StructInspector(super)

    def __init__(self, super):
        self.super = super

current_inspector = W_StructInspector(None)

class W_StructTypeDescriptor(W_Object):
    errorname = "struct-type-descriptor"
    _immutable_fields_ = ["value", "w_struct_type"]
    def __init__(self, value, w_struct_type):
        self.value = value
        self.w_struct_type = w_struct_type
    def tostring(self):
        return "#<struct-type:%s>" % self.value

class W_StructType(W_Object):
    errorname = "struct-type"
    _immutable_fields_ = ["desc", "super", "init_field_cnt", "auto_field_cnt", "total_field_cnt", "auto_v", "props", \
        "inspector", "immutables", "guard", "constr_name", "auto_values[:]", "offsets[:]"]
    @staticmethod
    def make(name, super_type, init_field_cnt, auto_field_cnt, auto_v, props, 
             inspector, proc_spec, immutables, guard, constr_name):
        w_struct_id = W_StructTypeDescriptor(name.value, None)
        if super_type is not w_false:
            assert isinstance(super_type, W_StructTypeDescriptor)
            w_super_type = super_type.w_struct_type
        else:
            w_super_type = None
        w_struct_type = W_StructType(w_struct_id, w_super_type, init_field_cnt, 
                                     auto_field_cnt, auto_v, props, inspector, 
                                     proc_spec, immutables, guard, constr_name)
        w_struct_id.w_struct_type = w_struct_type
        return w_struct_type
    
    @jit.unroll_safe
    def initialize_prop_list(self, props):
        proplist = values.from_list(props)
        self.props =  [(None, None)] * len(proplist)
        for i, prop in enumerate(proplist):
            w_car = prop.car()
            w_prop = prop.cdr()
            if w_car.is_prop_procedure():
                self.prop_procedure = w_prop
            self.props[i] = (w_car, w_prop)

    def __init__(self, struct_id, super_type, init_field_cnt, auto_field_cnt, 
                 auto_v, props, inspector, proc_spec, immutables, guard, constr_name):
        self.desc = struct_id
        self.super = super_type
        self.init_field_cnt = init_field_cnt.value
        self.auto_field_cnt = auto_field_cnt.value
        self.total_field_cnt = self.init_field_cnt + self.auto_field_cnt + \
            (super_type.total_field_cnt if isinstance(super_type, W_StructType) else 0)
        self.auto_v = auto_v
        self.prop_procedure = None
        self.initialize_prop_list(props)
        self.inspector = inspector
        self.proc_spec = proc_spec
        self.immutables = []
        if isinstance(proc_spec, W_Fixnum):
            self.immutables.append(proc_spec.value)
        for i in values.from_list(immutables):
            assert isinstance(i, values.W_Fixnum)
            self.immutables.append(i.value)
        self.guard = guard
        if isinstance(constr_name, W_Symbol):
            self.constr_name = constr_name.value
        else:
            self.constr_name = "make-" + struct_id.value

        self.auto_values = [self.auto_v] * self.auto_field_cnt
        self.isopaque = self.inspector is not w_false
        self.offsets = self.calculate_offsets()
        
        constr_class = W_StructConstructor if props is w_null else W_CallableStructConstructor
        self.constr = constr_class(self.desc, self.super, self.init_field_cnt, 
            self.auto_values, self.prop_procedure, self.props, self.proc_spec, 
            self.isopaque, self.guard, self.constr_name)
        self.pred = W_StructPredicate(self.desc)
        self.acc = W_StructAccessor(self.desc)
        self.mut = W_StructMutator(self.desc)

    @jit.unroll_safe
    def calculate_offsets(self):
        result = {}
        struct_type = self
        while isinstance(struct_type, W_StructType):
            result[struct_type.desc] = struct_type.total_field_cnt - \
            struct_type.init_field_cnt - struct_type.auto_field_cnt
            struct_type = struct_type.super
        return result

    @jit.elidable
    def get_offset(self, struct_id):
        return self.offsets.get(struct_id, -1)

    def make_struct_tuple(self):
        return [self.desc, self.constr, self.pred, self.acc, self.mut]

class W_CallableStruct(W_Procedure):
    errorname = "callable-struct"
    _immutable_fields_ = ["struct"]
    def __init__(self, struct):
        assert isinstance(struct, W_Struct)
        self.struct = struct

    @make_call_method(simple=False)
    def call(self, args, env, cont):
        if self.struct.proc_spec is not w_false:
            args = [self.struct.proc_spec] + args

        proc = self.struct.prop_procedure
        if isinstance(proc, W_Fixnum):
            proc = self.struct._get_list(proc.value) 
        else:
            args = [self.struct] + args
        # TODO: check arities
        return proc.call(args, env, cont)

class W_RootStruct(W_Object):
    errorname = "root-struct"
    _immutable_fields_ = ["type", "isopaque", "ref", "set"]

    def __init__(self, struct_id, isopaque):
        self.type = struct_id
        self.isopaque = isopaque

    @label
    def ref(self, struct_id, field, env, cont):
        raise NotImplementedError("base class")

    @label
    def set(self, struct_id, field, val, env, cont):
        raise NotImplementedError("base class")

    def vals(self):
        raise NotImplementedError("base class")

class W_Struct(W_RootStruct):
    errorname = "struct"
    _immutable_fields_ = ["values", "prop_procedure", "props", "proc_spec", "isopaque"]
    def __init__(self, struct_id, prop_procedure, props, proc_spec, isopaque):
        W_RootStruct.__init__(self, struct_id, isopaque)
        self.prop_procedure = prop_procedure
        self.props = props
        self.proc_spec = proc_spec

    def vals(self):
        return self._get_full_list()

    # Rather than reference functions, we store the continuations. This is
    # necessarray to get constant stack usage without adding extra preamble
    # continuations.
    @label
    def ref(self, struct_id, field, env, cont):
        from pycket.interpreter import return_value
        offset = self.type.w_struct_type.get_offset(struct_id)
        if offset == -1:
            raise SchemeException("cannot reference an identifier before its definition")
        result = self._get_list(field + offset)
        return return_value(result, env, cont)

    @label
    def set(self, struct_id, field, val, env, cont):
        from pycket.interpreter import return_value
        offset = self.type.w_struct_type.get_offset(struct_id)
        if offset == -1:
            raise SchemeException("cannot reference an identifier before its definition")
        self._set_list(field + offset, val)
        return return_value(w_void, env, cont)

    def tostring(self):
        if self.isopaque:
            result =  "#<%s>" % self.type.value
        else:
            result = "(%s %s)" % (self.type.value, ' '.join([val.tostring() for val in self.vals()]))
        return result

inline_small_list(W_Struct, immutable=False, attrname="values")

class W_StructRootConstructor(W_Procedure):
    _immutable_fields_ = ["struct_id", "super_type", "init_field_cnt", "auto_values", \
        "prop_procedure", "props", "proc_spec",  "isopaque", "guard", "name"]
    def __init__(self, struct_id, super_type, init_field_cnt, auto_values, 
        prop_procedure, props, proc_spec, isopaque, guard, name):
        self.struct_id = struct_id
        self.super_type = super_type
        self.init_field_cnt = init_field_cnt
        self.auto_values = auto_values
        self.prop_procedure = prop_procedure if prop_procedure \
            else (super_type.prop_procedure if isinstance(super_type, W_StructType) else None)
        self.props = props if props else (super_type.props if isinstance(super_type, W_StructType) else None)
        self.proc_spec = proc_spec if proc_spec \
            else (super_type.proc_spec if isinstance(super_type, W_StructType) else None)
        self.isopaque = isopaque
        self.guard = guard
        self.name = name

    def make_struct(self, field_values):
        raise NotImplementedError("abstract base class")

    @continuation
    def constr_proc_cont(self, field_values, env, cont, _vals):
        from pycket.interpreter import return_value
        if len(self.auto_values) > 0:
            field_values = field_values + self.auto_values
        result = self.make_struct(field_values)
        return return_value(result, env, cont)

    @jit.unroll_safe
    def _splice(self, array, array_len, index, insertion, insertion_len):
        new_len = array_len + insertion_len
        assert new_len >= 0
        new_array = [None] * new_len
        for pre_index in range(index):
            new_array[pre_index] = array[pre_index]
        for insert_index in range(insertion_len):
            new_array[index + insert_index] = insertion[insert_index]
        for post_index in range(index, array_len):
            new_array[post_index + insertion_len] = array[post_index]
        return new_array

    @continuation
    def constr_proc_wrapper_cont(self, field_values, issuper, env, cont, _vals):
        from pycket.interpreter import return_value, jump
        super_type = jit.promote(self.super_type)
        if isinstance(super_type, W_StructType):
            split_position = len(field_values) - self.init_field_cnt
            super_auto = super_type.constr.auto_values
            assert split_position >= 0
            field_values = self._splice(
                field_values, len(field_values), split_position, 
                super_auto, len(super_auto))
            return super_type.constr.code(field_values[:split_position], True, 
                env, self.constr_proc_cont(field_values, env, cont))
        else:
            if issuper:
                return jump(env, cont)
            else:
                return jump(env, self.constr_proc_cont(field_values, env, cont))

    def code(self, field_values, issuper, env, cont):
        from pycket.interpreter import jump
        if self.guard is w_false:
            return jump(env, self.constr_proc_wrapper_cont(field_values, issuper, env, cont))
        else:
            guard_args = field_values + [W_Symbol.make(self.struct_id.value)]
            jit.promote(self)
            return self.guard.call(guard_args, env, 
                self.constr_proc_wrapper_cont(field_values, issuper, env, cont))

    def call(self, args, env, cont):
        return self.code(args, False, env, cont)

    def tostring(self):
        return "#<procedure:%s>" % self.name

class W_StructConstructor(W_StructRootConstructor):
    def make_struct(self, field_values):
        return W_Struct.make(field_values, self.struct_id, self.prop_procedure, 
            self.props, self.proc_spec, self.isopaque)

class W_CallableStructConstructor(W_StructRootConstructor):
    def make_struct(self, field_values):
        struct = W_Struct.make(field_values, self.struct_id, self.prop_procedure, 
            self.props, self.proc_spec, self.isopaque)
        return W_CallableStruct(struct)

class W_StructPredicate(W_Procedure):
    errorname = "struct-predicate"
    _immutable_fields_ = ["struct_id"]
    def __init__ (self, struct_id):
        self.struct_id = struct_id

    @make_call_method([W_Object])
    def call(self, struct):
        if isinstance(struct, W_Struct):
            struct_type = struct.type.w_struct_type
            while isinstance(struct_type, W_StructType):
                if struct_type.desc == self.struct_id:
                    return w_true
                struct_type = struct_type.super
        return w_false
    def tostring(self):
        return "#<procedure:%s?>" % self.struct_id.value

class W_StructFieldAccessor(W_Procedure):
    errorname = "struct-field-accessor"
    _immutable_fields_ = ["accessor", "field"]
    def __init__ (self, accessor, field):
        assert isinstance(accessor, W_StructAccessor)
        self.accessor = accessor
        self.field = field

    @make_call_method([W_Object], simple=False)
    def call(self, struct, env, cont):
        if isinstance(struct, W_CallableStruct):
            struct = struct.struct
        assert isinstance(struct, W_RootStruct)
        return self.accessor.access(struct, self.field, env, cont)

class W_StructAccessor(W_Procedure):
    errorname = "struct-accessor"
    _immutable_fields_ = ["struct_id"]
    def __init__ (self, struct_id):
        self.struct_id = struct_id

    def access(self, struct, field, env, cont):
        from pycket.interpreter import jump
        return jump(env, struct.ref(self.struct_id, field.value, env, cont))

    call = make_call_method([W_Struct, W_Fixnum], simple=False)(access)

    def tostring(self):
        return "#<procedure:%s-ref>" % self.struct_id.value

class W_StructFieldMutator(W_Procedure):
    errorname = "struct-field-mutator"
    _immutable_fields_ = ["mutator", "field"]
    def __init__ (self, mutator, field):
        assert isinstance(mutator, W_StructMutator)
        self.mutator = mutator
        self.field = field

    @make_call_method([W_Object, W_Object], simple=False)
    def call(self, struct, val, env, cont):
        if isinstance(struct, W_CallableStruct):
            struct = struct.struct
        assert isinstance(struct, W_RootStruct)
        return self.mutator.mutate(struct, self.field, val, env, cont)

class W_StructMutator(W_Procedure):
    errorname = "struct-mutator"
    _immutable_fields_ = ["struct_id"]
    def __init__ (self, struct_id):
        self.struct_id = struct_id

    def mutate(self, struct, field, val, env, cont):
        from pycket.interpreter import jump
        return jump(env, struct.set(self.struct_id, field.value, val, env, cont))

    call = make_call_method([W_RootStruct, W_Fixnum, W_Object], simple=False)(mutate)

    def tostring(self):
        return "#<procedure:%s-set!>" % self.struct_id.value

class W_StructProperty(W_Object):
    errorname = "struct-type-property"
    _immutable_fields_ = ["name", "guard", "supers", "can_imp"]
    def __init__(self, name, guard, supers=w_null, can_imp=False):
        self.name = name.value
        self.guard = guard
        self.supers = values.from_list(supers) if supers is not values.w_null else []
        self.can_imp = can_imp
    def is_prop_procedure(self):
        if self is w_prop_procedure:
            return True
        elif len(self.supers) > 0:
            for super in self.supers:
                if super.car() is w_prop_procedure:
                    return True
        return False
    def tostring(self):
        return "#<struct-type-property:%s>"%self.name

w_prop_procedure = W_StructProperty(values.W_Symbol.make("prop:procedure"), w_false)

class W_StructPropertyPredicate(W_Procedure):
    errorname = "struct-property-predicate"
    _immutable_fields_ = ["property"]
    def __init__(self, prop):
        self.property = prop
    @make_call_method([W_Object])
    def call(self, arg):
        if isinstance(arg, W_Struct):
            props = arg.props
        elif isinstance(arg, W_CallableStruct):
            props = arg.struct.props
        else:
            return values.w_false
        for (p, val) in props:
            # FIXME: parent properties
            if p is self.property:
                return values.w_true
        return values.w_false
                
class W_StructPropertyAccessor(W_Procedure):
    errorname = "struct-property-accessor"
    _immutable_fields_ = ["property"]
    def __init__(self, prop):
        self.property = prop
    @make_call_method([W_Object])
    def call(self, arg):
        if isinstance(arg, W_Struct):
            props = arg.props
        elif isinstance(arg, W_CallableStruct):
            props = arg.struct.props
        else:
            raise SchemeException("%s-accessor: expected %s? but got %s"%(self.property.name, self.property.name, arg.tostring()))
        for (p, val) in props:
            # FIXME: parent properties
            if p is self.property:
                return val
        raise SchemeException("%s-accessor: expected %s? but got %s"%(self.property.name, self.property.name, arg.tostring()))
