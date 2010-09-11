#!/usr/bin/env python
# encoding: utf-8


import opcode
import types
import dis

locals().update(opcode.opmap)


def findNestedFuncs(fcode):
    # We use this function to recursively search for nested functions
    for const in fcode.co_consts:
        # fun��es
        if isinstance(const, types.CodeType):
            yield const
            for code in findNestedFuncs(const):
                yield code


def noself(func, inst):
    # A maior parte da m�gica est� aqui nesta fun��o..

    # Ela receber� a fun��o que define o m�todo a ser
    # modificado e a inst�ncia que deve aparecer l� dentro como 'self'
    
    # o que ela faz � simplesmente colocar no in�cio do m�todo o
    # equivalente � linha: self = inst

    # primeiro, precisamos do bytecode da fun��o
    code = func.func_code

    # agora precisamos dar uma estripada no objeto c�digo e retirar
    # todos os atributos para recri�-lo mais tarde... nem tudo aqui
    # ser� alterado, mas tirando tudo facilita depois

    argcount = code.co_argcount       # n�mero de par�metros
    nlocals = code.co_nlocals         # n�mero de vari�veis locais
    stacksize = code.co_stacksize     # tamanho m�ximo da pilha
    flags = code.co_flags             # algumas flags para o interpretador
    codestring = code.co_code         # o c�digo
    constants = code.co_consts        # as constantes na fun��o. 
    names = code.co_names             # nomes de globais usadas
    varnames = code.co_varnames       # nomes de vari�veis usadas
    filename = code.co_filename       # nome do arquivo
    name = code.co_name               # nome da fun��o
    firstlineno = code.co_firstlineno # primeira linha da fun��o
    lnotab = code.co_lnotab            
    freevars = code.co_freevars       # vari�veis livres
    cellvars = code.co_cellvars       # vari�veis usadas em fun��o aninhada

    # temos de descobrir se h� qualquer fun��o aninhada dentro de
    # func... para isso verificamos se h� qualquer objeto c�digo
    # definido como constante dentro do c�digo da fun��o, em caso
    # positivo, continua a busca recursivamente
    
    # primeiro, colocamos o nome 'self' na lista de nomes de
    # vari�veis... colocamos no final para evitar ter de mudar o
    # �ndice de todas as outras
    varnames += ('self',)

    # depois, fazemos a mesma coisa com a inst�ncia na lista de
    # constantes
    constants += (inst,)

    # como acrescentamos uma vari�vel, aumentamos o n�mero de
    # vari�veis locais
    nlocals += 1

    # convertemos a string de c�digo para uma lista com o valor
    # num�rico de cada byte
    bcode = map(ord, code.co_code)

    # ent�o colocamos no in�cio do c�digo as instru��es para fazer
    # a atribui��o self=inst
    bcode = [LOAD_CONST,        
             len(constants)-1,  # carrega a inst�ncia na pilha
             0,
             STORE_FAST,
             len(varnames)-1,   # atribui a inst�ncia a 'self'
             0] + bcode


    # agora vem a parte complicada... infelizmente, quando definimos
    # as chamadas a 'self' no c�digo sem estar definido localmente, o
    # interpretador vai busc�-lo como global, e n�o vai encontrar o
    # que definimos localmente logo agora... para consertar isso,
    # precisamos encontrar todas os acessos a globais e substituir
    # aqueles que tentam acessar o 'self' como global por um acesso
    # local

    # para facilitar, vamos usar um iterador...
    itercode = iter(enumerate(bcode))
    
    while 1:
        try:
            i, op = itercode.next()
            # se a instru��o precisa de argumentos, pode nos
            # interessar ou n�o, mas de qualquer maneira precisamos
            # pular os bytes dos argumentos para n�o confundir um
            # valor com instru��o...
            if op >= opcode.HAVE_ARGUMENT:
                # os argumentos vem nos dois bytes seguintes... 
                oparg = itercode.next()[1] + itercode.next()[1]*256
                # procuramos por LOAD_GLOBAL
                if op == LOAD_GLOBAL:
                    # o argumento para LOAD_GLOBAL � o �ndice do nome
                    # da vari�vel em 'names'... se � 'self',
                    # ent�o � o que procuramos!
                    if names[oparg] == 'self':
                        # substitu�mos a instru��o LOAD_GLOBAL por LOAD_FAST
                        bcode[i] = LOAD_FAST
                        # substitu�mos o argumento para o �ndice do
                        # nome 'self' na lista 'varnames'
                        bcode[i+1] = len(varnames)-1
                        # a menos que a fun��o tenha mais de 255
                        # vari�veis, n�o teremos problemas aqui e
                        # podemos colocar 0
                        bcode[i+2] = 0

        except StopIteration:
            # saia do loop quando o iterador esgotar...
            break

    # transformamos a lista com o c�digo num�rico novamente em string
    codestring = ''.join(map(chr, bcode))

    # recriamos o objeto c�digo com os valores e byte-code novo: muda
    # apenas 'varnames', 'constants', 'nlocals', e o c�digo, claro...
    ncode = types.CodeType(argcount, nlocals, stacksize, flags, codestring,
                           constants, names, varnames, filename, name,
                           firstlineno, lnotab, freevars, cellvars)
    # note que como 'self' vem originalmente como global, o nome vem
    # em 'names', mas n�o podemos remov�-lo para n�o atrapalhar com os
    # �ndices de outras vari�veis...

    # finalmente, recriamos e retornamos a fun��o, com tudo de antes,
    # mas com o c�digo novo, alterado
    nfunc = types.FunctionType(ncode, func.func_globals, func.func_name,
                               func.func_defaults, func.func_closure)

    return nfunc


# Depois disso tudo, o resto � moleza...

class NoSelfMethod(object):
    # um descriptor que implementa (mais ou menos) o mesmo que os
    # m�todos normais (j� que a classe MethodType original n�o permite
    # heran�a)....
    def __init__(self, func, instance, cls):
        self.im_func = func
        self.im_self = instance
        self.im_class = cls

    def __get__(self, obj, cls):
        return NoSelfMethod(self.im_func, obj, cls)

    def __call__(self, *args, **kwds):
        # com a diferen�a de que quando � chamado com uma inst�ncia,
        # ele usa nossa fun��o nofunc() para criar a nova vers�o
        # inserindo o 'self' (sim, ele recria a fun��o fazendo aquilo
        # tudo cada vez que o m�todo � chamado!)
        if self.im_self is None:
            return self.im_func(*args, **kwds)
        else:
            func = noself(self.im_func, self.im_self)
            return func(*args, **kwds)


class NoSelfType(type):
    # E finalmente, uma metaclasse que faz com que suas classes usem o
    # nosso m�todo especial 
    def __new__(mcls, name, bases, dic):
        for k, v in dic.items():
            if callable(v):
                dic[k] = NoSelfMethod(v, None, None)

        return type.__new__(NoSelfType, name, bases, dic)
        

def test():

    # Testando ...

    # Uma global s� para garantir que elas n�o foram alteradas...
    bar = 'bar'

    class C(object):
        __metaclass__ = NoSelfType

        def __init__(a, b, c=None):
            print 'Look mom... no self!', self
            # confirmando que o 'self' apareceu aqui
            print 'I am', self, 'they called me with', a, b, c

        def m(obj):
            # confirmando que o 'self' que aparece aqui e o objeto
            # criado s�o de fato os mesmos
            assert obj is self
            # confirmando que a global est� ok
            assert bar == 'bar'

            def f():
                # FIXME: infelizmente, fun��es aninhadas usam a
                # instru��o LOAD_DEREF para encontrar vari�veis do
                # escopo anterior, que aparecem naquela lista
                # 'cellvars' l� em cima, ent�o esta fun��o f() n�o vai
                # encontrar o 'self' pois tenta procur�-lo como
                # global, o que significa que teremos de fazer outra
                # altera��o aqui tamb�m, bem mais complicada... por
                # via das d�vidas, vamos testar e conferir que d�
                # erro em todas as implementa��es e vers�es...
                try:
                    assert obj is self
                    raise AssertionError('self found from nested function?')
                except NameError:
                    pass
            f()

            # � isso a�... 

    o = C(1, 2, c='foo')
    o.m(o)
        
        
if __name__ == '__main__':
    test()





