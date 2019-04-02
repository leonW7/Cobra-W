# -*- coding: utf-8 -*-

"""
    parser
    ~~~~~~

    Implements Code Parser

    :author:    BlBana <635373043@qq.com>
    :homepage:  https://github.com/wufeifei/cobra
    :license:   MIT, see LICENSE for more details.
    :copyright: Copyright (c) 2017 Feei. All rights reserved
"""
from phply.phplex import lexer  # 词法分析
from phply.phpparse import make_parser  # 语法分析
from phply import phpast as php
from .log import logger
import re
import codecs

with_line = True
scan_results = []  # 结果存放列表初始化
is_repair_functions = []  # 修复函数初始化


def export(items):
    result = []
    if items:
        for item in items:
            if hasattr(item, 'generic'):
                item = item.generic(with_lineno=with_line)
            result.append(item)
    return result


def export_list(params, export_params):
    """
    将params中嵌套的多个列表，导出为一个列表
    :param params:
    :param export_params:
    :return:
    """
    for param in params:
        if isinstance(param, list):
            export_params = export_list(param, export_params)

        else:
            export_params.append(param)

    return export_params


def get_all_params(nodes):  # 用来获取调用函数的参数列表，nodes为参数列表
    """
    获取函数结构的所有参数
    :param nodes:
    :return:
    """
    params = []
    export_params = []  # 定义空列表，用来给export_list中使用
    for node in nodes:
        if isinstance(node.node, php.FunctionCall):  # 函数参数来自另一个函数的返回值
            params = get_all_params(node.node.params)

        else:
            if isinstance(node.node, php.Variable):
                params.append(node.node.name)

            if isinstance(node.node, php.BinaryOp):
                params = get_binaryop_params(node.node)
                params = export_list(params, export_params)

            if isinstance(node.node, php.ArrayOffset):
                param = get_node_name(node.node.node)
                params.append(param)

            if isinstance(node.node, php.Cast):
                param = get_cast_params(node.node.expr)
                params.append(param)

            if isinstance(node.node, php.Silence):
                param = get_silence_params(node.node)
                params.append(param)

    return params


def get_silence_params(node):
    """
    用来提取Silence类型中的参数
    :param node:
    :return:
    """
    param = []
    if isinstance(node.expr, php.Variable):
        param = get_node_name(node.expr)

    if isinstance(node.expr, php.FunctionCall):
        param.append(node.expr)

    if isinstance(node.expr, php.Eval):
        param.append(node.expr)

    if isinstance(node.expr, php.Assignment):
        param.append(node.expr)

    return param


def get_cast_params(node):
    """
    用来提取Cast类型中的参数
    :param node:
    :return:
    """
    param = []
    if isinstance(node, php.Silence):
        param = get_node_name(node.expr)

    return param


def get_binaryop_params(node):  # 当为BinaryOp类型时，分别对left和right进行处理，取出需要的变量
    """
    用来提取Binaryop中的参数
    :param node:
    :return:
    """
    # logger.debug('[AST] Binaryop --> {node}'.format(node=node))
    params = []
    buffer_ = []

    if isinstance(node.left, php.Variable):
        params.append(node.left.name)
    else:
        params = get_binaryop_deep_params(node.left, params)

    if isinstance(node.right, php.Variable):
        params.append(node.right.name)
    else:
        params = get_binaryop_deep_params(node.right, params)

    params = export_list(params, buffer_)
    return params


def get_binaryop_deep_params(node, params):  # 取出right，left不为变量时，对象结构中的变量
    """
    取出深层的变量名
    :param node: node为上一步中的node.left或者node.right节点
    :param params:
    :return:
    """
    if isinstance(node, php.ArrayOffset):  # node为数组，取出数组变量名
        param = get_node_name(node.node)
        params.append(param)

    if isinstance(node, php.BinaryOp):  # node为BinaryOp，递归取出其中变量
        param = get_binaryop_params(node)
        params.append(param)

    if isinstance(node, php.FunctionCall):  # node为FunctionCall，递归取出其中变量名
        params = get_all_params(node.params)

    if isinstance(node, php.Constant):
        params.append(node)

    if type(node) is str:
        params.append(node)

    return params


def get_expr_name(node):  # expr为'expr'中的值
    """
    获取赋值表达式的表达式部分中的参数名-->返回用来进行回溯
    :param node:
    :return:
    """
    param_lineno = 0
    is_re = False
    if isinstance(node, php.ArrayOffset):  # 当赋值表达式为数组
        param_expr = get_node_name(node.node)  # 返回数组名
        param_lineno = node.node.lineno

    elif isinstance(node, php.Variable):  # 当赋值表达式为变量
        param_expr = node.name  # 返回变量名
        param_lineno = node.lineno

    elif isinstance(node, php.FunctionCall):  # 当赋值表达式为函数
        param_expr = get_all_params(node.params)  # 返回函数参数列表
        param_lineno = node.lineno
        is_re = is_repair(node.name)  # 调用了函数，判断调用的函数是否为修复函数

    elif isinstance(node, php.BinaryOp):  # 当赋值表达式为BinaryOp
        param_expr = get_binaryop_params(node)
        param_lineno = node.lineno

    else:
        param_expr = node

    return param_expr, param_lineno, is_re


def get_node_name(node):  # node为'node'中的元组
    """
    获取Variable类型节点的name
    :param node:
    :return:
    """
    if isinstance(node, php.Variable):
        return node.name  # 返回此节点中的变量名

    if isinstance(node, php.ObjectProperty):
        return node


def get_filename(node, file_path):  # 获取filename
    """
    获取
    :param node: 
    :param file_path: 
    :return: 
    """
    filename = node.expr
    filenames = []
    if isinstance(filename, php.BinaryOp):
        filenames = get_binaryop_params(filename)

    elif type(filename) is str:
        filenames = [filename]

    for i in range(len(filenames)):
        if isinstance(filenames[i], php.Constant):
            constant_node = filenames[i]
            constant_node_name = constant_node.name

            f = codecs.open(file_path, 'r', encoding='utf-8', errors='ignore')
            file_content = f.read()
            parser = make_parser()
            all_nodes = parser.parse(file_content, debug=False, lexer=lexer.clone(), tracking=with_line)

            for node in all_nodes:
                if isinstance(node, php.FunctionCall) and node.name == "define":
                    define_params = node.params

                    if len(define_params) == 2 and define_params[0].node == constant_node_name:
                        filenames[i] = define_params[1].node

            if isinstance(filenames[i], php.Constant):  # 如果还没找到该常量，暂时退出
                logger.warning("[AST] [INCLUDE FOUND] Can't found this constart {}, pass it ".format(filenames[i]))
                filenames[i] = "not_found"

    return filenames


def is_repair(expr):
    """
    判断赋值表达式是否出现过滤函数，如果已经过滤，停止污点回溯，判定漏洞已修复
    :param expr: 赋值表达式
    :return:
    """
    is_re = False  # 是否修复，默认值是未修复
    global is_repair_functions
    if expr in is_repair_functions:
        logger.debug("[AST] function {} in is_repair_functions, The vulnerability does not exist ")
        is_re = True
    return is_re


def is_sink_function(param_expr, function_params):
    """
    判断自定义函数的入参-->判断此函数是否是危险函数
    :param param_expr:
    :param function_params:
    :return:
    """
    is_co = -1
    cp = None
    if function_params is not None:
        for function_param in function_params:
            if param_expr == function_param:
                is_co = 2
                cp = function_param
                logger.debug('[AST] is_sink_function --> {function_param}'.format(function_param=cp))
    return is_co, cp


def is_controllable(expr, flag=None):  # 获取表达式中的变量，看是否在用户可控变量列表中
    """
    判断赋值表达式是否是用户可控的
    :param expr:
    :return:
    """
    controlled_params = [
        '$_GET',
        '$_POST',
        '$_REQUEST',
        '$_COOKIE',
        '$_FILES',
        # '$_SERVER', # 暂时去掉了，误报率太高了
        '$HTTP_POST_FILES',
        '$HTTP_COOKIE_VARS',
        '$HTTP_REQUEST_VARS',
        '$HTTP_POST_VARS',
        '$HTTP_RAW_POST_DATA',
        '$HTTP_GET_VARS'
    ]
    if isinstance(expr, php.ObjectProperty):
        return 3, php.Variable(expr)

    if isinstance(expr, php.New) or isinstance(expr, php.MethodCall) or isinstance(expr, php.FunctionCall):
        return 3, php.Variable(expr)

    if isinstance(expr, php.Variable):
        expr = expr.name

    if expr in controlled_params:  # 当为可控变量时 返回1
        logger.debug('[AST] is_controllable --> {expr}'.format(expr=expr))
        if flag:
            return 1, expr
        return 1, php.Variable(expr)

    try:
        if expr.startswith("$"):
            if flag:
                return 3, expr
            return 3, php.Variable(expr)
    except AttributeError:
        pass
    except:
        raise

    return -1, php.Variable(expr)


# def function_deep_back(param, nodes, function_params):  # 回溯函数定义位置
#     """
#     递归回溯函数定义位置，传入param类型不同
#     :param param:
#     :param nodes:
#     :return:
#     """
# function_name = param.name

# is_co = 3
# cp = param
# expr_lineno = 0

# print nodes

# for node in nodes[::-1]:
#     if isinstance(node, php.Function):
#         if node.name == function_name:
#             function_nodes = node.nodes
#
#             # 进入递归函数内语句
#             for function_node in function_nodes:
#                 if isinstance(function_node, php.Return):
#                     return_node = function_node.node
#                     return_param = return_node.node
#                     is_co, cp, expr_lineno = parameters_back(return_param, function_nodes, function_params)
#
# return is_co, cp, expr_lineno


def function_back(param, nodes, function_params, vul_function=None):  # 回溯函数定义位置
    """
    递归回溯函数定义位置，传入param类型不同
    :param function_params: 
    :param vul_function: 
    :param param: 
    :param nodes: 
    :return: 
    """
    function_name = param.name

    is_co = 3
    cp = param
    expr_lineno = 0

    for node in nodes[::-1]:
        if isinstance(node, php.Function):
            if node.name == function_name:
                function_nodes = node.nodes

                # 进入递归函数内语句
                for function_node in function_nodes:
                    if isinstance(function_node, php.Return):
                        return_node = function_node.node
                        return_param = return_node.node
                        is_co, cp, expr_lineno = parameters_back(return_param, function_nodes, function_params,
                                                                 vul_function=vul_function)

    return is_co, cp, expr_lineno


def array_back(param, nodes, vul_function=None):  # 回溯数组定义赋值
    """
    递归回溯数组赋值定义
    :param vul_function: 
    :param param: 
    :param nodes: 
    :return: 
    """
    param_name = param.node.name
    param_expr = param.expr

    is_co = 3
    cp = param
    expr_lineno = 0

    # print nodes
    for node in nodes[::-1]:
        if isinstance(node, php.Assignment):
            param_node_name = get_node_name(node.node)
            param_node = node.node
            param_node_expr = node.expr

            if param_node_name == param_name:  # 处理数组中值被改变的问题
                if isinstance(node.expr, php.Array):
                    for p_node in node.expr.nodes:
                        if p_node.key == param_expr:
                            if isinstance(p_node.value, php.ArrayOffset):  # 如果赋值值仍然是数组，先经过判断在进入递归
                                is_co, cp = is_controllable(p_node.value.node.name)

                                if is_co != 1:
                                    is_co, cp, expr_lineno = array_back(param, nodes)

                            else:
                                n_node = php.Variable(p_node.value)
                                is_co, cp, expr_lineno = parameters_back(n_node, nodes, vul_function=vul_function)

            if param == param_node:  # 处理数组一次性赋值，左值为数组
                if isinstance(param_node_expr, php.ArrayOffset):  # 如果赋值值仍然是数组，先经过判断在进入递归
                    is_co, cp = is_controllable(param_node_expr.node.name)

                    if is_co != 1:
                        is_co, cp, expr_lineno = array_back(param, nodes)
                else:
                    is_co, cp = is_controllable(param_node_expr)

                    if is_co != 1 and is_co != -1:
                        n_node = php.Variable(param_node_expr.node.value)
                        is_co, cp, expr_lineno = parameters_back(n_node, nodes, vul_function=vul_function)

    return is_co, cp, expr_lineno


def class_back(param, node, lineno, vul_function=None):
    """
    回溯类中变量
    :param vul_function: 
    :param param: 
    :param node: 
    :param lineno: 
    :return: 
    """
    class_name = node.name
    class_nodes = node.nodes

    vul_nodes = []
    for class_node in class_nodes:
        if class_node.lineno < int(lineno):
            vul_nodes.append(class_node)

    is_co, cp, expr_lineno = parameters_back(param, vul_nodes, lineno=lineno, vul_function=vul_function)

    if is_co == 1 or is_co == -1:  # 可控或者不可控，直接返回
        return is_co, cp, expr_lineno
    elif is_co == 3:
        for class_node in class_nodes:
            if isinstance(class_node, php.Method) and class_node.name == '__construct':
                class_node_params = class_node.params
                constructs_nodes = class_node.nodes

                # 递归析构函数
                is_co, cp, expr_lineno = parameters_back(param, constructs_nodes, function_params=class_node_params,
                                                         lineno=lineno, vul_function=vul_function)

                if is_co == 3:
                    # 回溯输入参数
                    for param in class_node_params:
                        if param.name == cp.name:
                            logger.info(
                                "[Deep AST] Now vulnerability function in class from class {}() param {}".format(
                                    class_name, cp.name))

                            is_co = 4
                            cp = tuple([node, param, class_node_params])
                            return is_co, cp, 0

    return is_co, cp, expr_lineno


def new_class_back(param, nodes, vul_function=None):
    """
    分析新建的class，自动进入tostring函数
    :param vul_function: 
    :param param: 
    :param nodes: 
    :return: 
    """
    param = param.name
    param_name = param.name
    param_params = param.params

    is_co = -1
    cp = param
    expr_lineno = 0

    for node in nodes:
        if isinstance(node, php.Class) and param_name == node.name:
            class_nodes = node.nodes

            for class_node in class_nodes:
                if isinstance(class_node, php.Method) and class_node.name == '__toString':
                    tostring_nodes = class_node.nodes
                    logger.debug("[AST] try to analysize class {}() function tostring...".format(param_name))

                    for tostring_node in tostring_nodes:
                        if isinstance(tostring_node, php.Return):
                            return_param = tostring_node.node
                            is_co, cp, expr_lineno = parameters_back(return_param, tostring_nodes,
                                                                     vul_function=vul_function)
                            return is_co, cp, expr_lineno

        else:
            is_co = 3
            cp = php.Variable(param)

    return is_co, cp, expr_lineno


def parameters_back(param, nodes, function_params=None, lineno=0,
                    function_flag=0, vul_function=None):  # 用来得到回溯过程中的被赋值的变量是否与敏感函数变量相等,param是当前需要跟踪的污点
    """
    递归回溯敏感函数的赋值流程，param为跟踪的污点，当找到param来源时-->分析复制表达式-->获取新污点；否则递归下一个节点
    :param vul_function: 
    :param param:
    :param nodes:
    :param function_params:
    :param lineno
    :param function_flag: 是否在函数、方法内的标志位
    :return:
    """

    if isinstance(param, php.FunctionCall) or isinstance(param, php.MethodCall):  # 当污点为寻找函数时，递归进入寻找函数
        logger.debug("[AST] AST analysis for FunctionCall or MethodCall {} in line {}".format(param.name, param.lineno))
        is_co, cp, expr_lineno = function_back(param, nodes, function_params)
        return is_co, cp, expr_lineno

    if isinstance(param, php.ArrayOffset):  # 当污点为数组时，递归进入寻找数组声明或赋值
        logger.debug("[AST] AST analysis for ArrayOffset  in line {}".format(param.lineno))
        is_co, cp, expr_lineno = array_back(param, nodes)
        return is_co, cp, expr_lineno

    if isinstance(param, php.New) or (hasattr(param, "name") and isinstance(param.name, php.New)):  # 当污点为新建类事，进入类中tostring函数分析
        logger.debug("[AST] AST analysis for New Class {} in line {}".format(param.name, param.lineno))
        is_co, cp, expr_lineno = new_class_back(param, nodes)
        return is_co, cp, expr_lineno

    expr_lineno = 0  # source所在行号
    if hasattr(param, "name"):
        # param_name = param.name
        param_name = get_node_name(param)
    else:
        param_name = param

    is_co, cp = is_controllable(param_name)

    if len(nodes) != 0:
        node = nodes[len(nodes) - 1]

        if isinstance(node, php.Assignment):  # 回溯的过程中，对出现赋值情况的节点进行跟踪
            param_node = get_node_name(node.node)  # param_node为被赋值的变量
            param_expr, expr_lineno, is_re = get_expr_name(node.expr)  # param_expr为赋值表达式,param_expr为变量或者列表

            if param_name == param_node and is_re is True:
                is_co = 2
                cp = param
                return is_co, cp, expr_lineno

            if param_name == param_node and not isinstance(param_expr, list):  # 找到变量的来源，开始继续分析变量的赋值表达式是否可控
                logger.debug(
                    "[AST] Find {}={} in line {}, start ast for param {}".format(param_name, param_expr, expr_lineno,
                                                                                 param_expr))
                is_co, cp = is_controllable(param_expr)  # 开始判断变量是否可控

                if is_co != 1 and is_co != 3:
                    is_co, cp = is_sink_function(param_expr, function_params)

                if isinstance(node.expr, php.ArrayOffset):
                    param = node.expr
                else:
                    param = php.Variable(param_expr)  # 每次找到一个污点的来源时，开始跟踪新污点，覆盖旧污点

            if param_name == param_node and isinstance(node.expr, php.FunctionCall):  # 当变量来源是函数时，处理函数内容
                function_name = node.expr.name
                param = node.expr  # 如果没找到函数定义，则将函数作为变量回溯

                logger.debug(
                    "[AST] Find {} from FunctionCall for {} in line {}, start ast in function {}".format(param_name,
                                                                                                         function_name,
                                                                                                         node.lineno,
                                                                                                         function_name))

                for node in nodes[::-1]:
                    if isinstance(node, php.Function):
                        if node.name == function_name:
                            function_nodes = node.nodes

                            # 进入递归函数内语句
                            for function_node in function_nodes:
                                if isinstance(function_node, php.Return):
                                    return_node = function_node.node
                                    return_param = return_node.node
                                    is_co, cp, expr_lineno = parameters_back(return_param, function_nodes,
                                                                             function_params, lineno, function_flag=1,
                                                                             vul_function=vul_function)

            if param_name == param_node and isinstance(param_expr, list):
                logger.debug(
                    "[AST] Find {} from list for {} in line {}, start ast for list {}".format(param_name,
                                                                                              param_expr,
                                                                                              node.lineno,
                                                                                              param_expr))
                for expr in param_expr:
                    param = expr
                    is_co, cp = is_controllable(expr)

                    if is_co == 1:
                        return is_co, cp, expr_lineno

                    param = php.Variable(param)
                    _is_co, _cp, expr_lineno = parameters_back(param, nodes[:-1], function_params, lineno,
                                                               function_flag=1, vul_function=vul_function)

                    if _is_co != -1:  # 当参数可控时，值赋给is_co 和 cp，有一个参数可控，则认定这个函数可能可控
                        is_co = _is_co
                        cp = _cp

        elif isinstance(node, php.Function) or isinstance(node, php.Method) and function_flag == 0:
            function_nodes = node.nodes
            function_lineno = node.lineno
            function_params = node.params
            vul_nodes = []

            logger.debug(
                "[AST] param {} line {} in function {} line {}, start ast in function".format(param_name,
                                                                                              node.lineno,
                                                                                              node.name,
                                                                                              function_lineno))

            for function_node in function_nodes:
                if function_node is not None and int(function_lineno) <= function_node.lineno < int(lineno):
                    vul_nodes.append(function_node)

            if len(vul_nodes) > 0:
                is_co, cp, expr_lineno = parameters_back(param, function_nodes, function_params, function_lineno,
                                                         function_flag=1, vul_function=vul_function)

            if is_co == 3:  # 出现新的敏感函数，重新生成新的漏洞结构，进入新的遍历结构
                for node_param in node.params:
                    if node_param.name == cp.name:
                        logger.debug(
                            "[AST] param {} line {} in function_params, start new rule for function {}".format(
                                param_name, node.lineno, node.name))

                        if vul_function is None or node.name != vul_function:
                            logger.info(
                                "[Deep AST] Now vulnerability function from function {}() param {}".format(node.name,
                                                                                                           cp.name))

                            is_co = 4
                            cp = tuple([node, param])
                            return is_co, cp, 0
                        else:
                            logger.info(
                                "[Deep AST] Recursive problems may exist in the code, exit the new rules generated..."
                            )
                            # 无法解决递归，直接退出
                            is_co = -1
                            return is_co, cp, 0

        elif isinstance(node, php.Class):
            is_co, cp, expr_lineno = class_back(param, node, lineno, vul_function=vul_function)
            return is_co, cp, expr_lineno

        elif isinstance(node, php.If):
            logger.debug(
                "[AST] param {} line {} in if/else, start ast in if/else".format(param_name, node.lineno))

            if isinstance(node.node, php.Block):  # if里可能是代码块，也可能就一句语句
                if_nodes = node.node.nodes
                if_node_lineno = node.node.lineno
            elif node.node is not None:
                if_nodes = [node.node]
                if_node_lineno = node.node.lineno
            else:
                if_nodes = []
                if_node_lineno = 0

            # 进入分析if内的代码块，如果返回参数不同于进入参数，那么在不同的代码块中，变量值不同，不能统一处理，需要递归进入不同的部分
            is_co, cp, expr_lineno = parameters_back(param, if_nodes, function_params, if_node_lineno,
                                                     function_flag=1, vul_function=vul_function)

            if is_co == 3 and cp != param:  # 理由如上
                is_co, cp, expr_lineno = parameters_back(param, nodes[:-1], function_params, lineno,
                                                         function_flag=1, vul_function=vul_function)  # 找到可控的输入时，停止递归
                return is_co, cp, expr_lineno

            if is_co is not 1 and node.elseifs != []:  # elseif可能有多个，所以需要列表

                for node_elseifs_node in node.elseifs:
                    if isinstance(node_elseifs_node.node, php.Block):
                        elif_nodes = node_elseifs_node.node.nodes
                        elif_node_lineno = node_elseifs_node.node.lineno
                    elif node_elseifs_node.node is not None:
                        elif_nodes = [node_elseifs_node.node]
                        elif_node_lineno = node_elseifs_node.node.lineno
                    else:
                        elif_nodes = []
                        elif_node_lineno = 0

                    is_co, cp, expr_lineno = parameters_back(param, elif_nodes, function_params, elif_node_lineno,
                                                             function_flag=1, vul_function=vul_function)

                    if is_co == 3 and cp != param:  # 理由如上
                        is_co, cp, expr_lineno = parameters_back(param, nodes[:-1], function_params, lineno,
                                                                 function_flag=1,
                                                                 vul_function=vul_function)  # 找到可控的输入时，停止递归
                        return is_co, cp, expr_lineno
                    else:
                        break

            if is_co is not 1 and node.else_ != [] and node.else_ is not None:
                if isinstance(node.else_.node, php.Block):
                    else_nodes = node.else_.node.nodes
                    else_node_lineno = node.else_.node.lineno
                elif node.else_.node is not None:
                    else_nodes = [node.else_.node]
                    else_node_lineno = node.else_.node.lineno
                else:
                    else_nodes = []
                    else_node_lineno = 0

                is_co, cp, expr_lineno = parameters_back(param, else_nodes, function_params, else_node_lineno,
                                                         function_flag=1, vul_function=vul_function)

                if is_co == 3 and cp != param:  # 理由如上
                    is_co, cp, expr_lineno = parameters_back(param, nodes[:-1], function_params, lineno,
                                                             function_flag=1,
                                                             vul_function=vul_function)  # 找到可控的输入时，停止递归
                    return is_co, cp, expr_lineno

        elif isinstance(node, php.For):
            for_nodes = node.node.nodes
            for_node_lineno = node.node.lineno

            logger.debug(
                "[AST] param {} line {} in for, start ast in for".format(param_name, for_node_lineno))

            is_co, cp, expr_lineno = parameters_back(param, for_nodes, function_params, for_node_lineno,
                                                     function_flag=1, vul_function=vul_function)

        if is_co == 3 or int(lineno) == node.lineno:  # 当is_co为True时找到可控，停止递归
            is_co, cp, expr_lineno = parameters_back(param, nodes[:-1], function_params, lineno,
                                                     function_flag=1, vul_function=vul_function)  # 找到可控的输入时，停止递归

    elif len(nodes) == 0 and function_params is not None:  # 当敏感函数在函数中时，function_params不为空，这时应进入自定义敏感函数逻辑
        for function_param in function_params:
            if function_param == param:
                logger.debug(
                    "[AST] param {} in function_params, start new rule".format(param_name))
                is_co = 2
                cp = function_param

    return is_co, cp, expr_lineno


def deep_parameters_back(param, back_node, function_params, count, file_path, lineno=0, vul_function=None):
    """
    深度递归遍历
    :param vul_function: 
    :param lineno: 
    :param param: 
    :param back_node:
    :param function_params: 
    :param file_path: 
    :return: 
    """
    count += 1

    is_co, cp, expr_lineno = parameters_back(param, back_node, function_params, lineno, vul_function=vul_function)

    if count > 20:
        logger.warning("[Deep AST] depth too big, auto exit...")
        return is_co, cp, expr_lineno

    if is_co == 3:
        logger.debug("[Deep AST] try to find include, start deep AST for {}".format(cp))

        for node in back_node[::-1]:
            if isinstance(node, php.Include):
                #  拼接路径需要专门处理，暂时先这样
                filename = get_filename(node, file_path)
                file_path_list = re.split(r"[\/\\]", file_path)
                file_path_list.pop()
                file_path_list += filename
                if "not_found" in filename:
                    continue
                file_path_name = "/".join(file_path_list)

                try:
                    logger.debug("[Deep AST] open new file {file_path}".format(file_path=file_path_name))
                    # f = open(file_path_name, 'r')
                    f = codecs.open(file_path_name, "r", encoding='utf-8', errors='ignore')
                    file_content = f.read()
                except:
                    logger.warning("[Deep AST] error to open new file...continue")
                    continue

                parser = make_parser()
                all_nodes = parser.parse(file_content, debug=False, lexer=lexer.clone(), tracking=with_line)
                node = cp
                # node = php.Variable(cp)

                is_co, cp, expr_lineno = deep_parameters_back(node, all_nodes, function_params, count, file_path_name,
                                                              lineno, vul_function=vul_function)
                if is_co == -1:
                    break

    return is_co, cp, expr_lineno


def get_function_node(nodes, s_lineno, e_lineno):
    """
    获取node列表中的指定行的node
    :param nodes: 
    :param s_lineno: 
    :param e_lineno: 
    :return: 
    """
    result = []

    for node in nodes:
        if node.lineno == e_lineno:
            result.append(node)
            break
        if node.lineno == s_lineno:
            result.append(node)
    return result


def get_function_params(nodes):
    """
    获取用户自定义函数的所有入参
    :param nodes: 自定义函数的参数部分
    :return: 以列表的形式返回所有的入参
    """
    params = []
    for node in nodes:

        if isinstance(node, php.FormalParameter):
            params.append(node.name)

    return params


def anlysis_params(param, code_content, file_path, lineno, vul_function=None, repair_functions=None):
    """
    在cast调用时做中转数据预处理
    :param repair_functions: 
    :param vul_function: 
    :param lineno: 
    :param param: 
    :param code_content: 
    :param file_path: 
    :return: 
    """
    global is_repair_functions
    count = 0
    function_params = None
    if repair_functions is not None:
        is_repair_functions = repair_functions

    if type(param) is str and "->" in param:
        param_left = php.Variable(param.split("->")[0])
        param_right = param.split("->")[1]
        param = php.ObjectProperty(param_left, param_right)

    param = php.Variable(param)
    parser = make_parser()
    all_nodes = parser.parse(code_content, debug=False, lexer=lexer.clone(), tracking=with_line)

    # 做一次处理，解决Variable(Variable('$id'))的问题
    while isinstance(param.name, php.Variable):
        param = param.name

    logger.debug("[AST] AST to find param {}".format(param))

    vul_nodes = []
    for node in all_nodes:
        if node is not None and node.lineno <= int(lineno):
            vul_nodes.append(node)

    is_co, cp, expr_lineno = deep_parameters_back(param, vul_nodes, function_params, count, file_path, lineno,
                                                  vul_function=vul_function)

    return is_co, cp, expr_lineno


def anlysis_function(node, back_node, vul_function, function_params, vul_lineno, file_path=None):
    """
    对用户自定义的函数进行分析-->获取函数入参-->入参用经过赋值流程，进入sink函数-->此自定义函数为危险函数
    :param file_path: 
    :param node:
    :param back_node:
    :param vul_function:
    :param function_params:
    :param vul_lineno:
    :return:
    """
    global scan_results
    try:
        if node.name == vul_function and int(node.lineno) == int(vul_lineno):  # 函数体中存在敏感函数，开始对敏感函数前的代码进行检测
            for param in node.params:
                if isinstance(param.node, php.Variable):
                    analysis_variable_node(param.node, back_node, vul_function, vul_lineno, function_params,
                                           file_path=file_path)

                if isinstance(param.node, php.FunctionCall):
                    analysis_functioncall_node(param.node, back_node, vul_function, vul_lineno, function_params,
                                               file_path=file_path)

                if isinstance(param.node, php.BinaryOp):
                    analysis_binaryop_node(param.node, back_node, vul_function, vul_lineno, function_params,
                                           file_path=file_path)

                if isinstance(param.node, php.ArrayOffset):
                    analysis_arrayoffset_node(param.node, vul_function, vul_lineno)

    except Exception as e:
        logger.debug(e)


def analysis_functioncall(node, back_node, vul_function, vul_lineno):
    """
    调用FunctionCall-->判断调用Function是否敏感-->get params获取所有参数-->开始递归判断
    :param node:
    :param back_node:
    :param vul_function:
    :param vul_lineno
    :return:
    """
    global scan_results
    try:
        if node.name == vul_function and int(node.lineno) == int(vul_lineno):  # 定位到敏感函数
            for param in node.params:
                if isinstance(param.node, php.Variable):
                    analysis_variable_node(param.node, back_node, vul_function, vul_lineno)

                if isinstance(param.node, php.FunctionCall):
                    analysis_functioncall_node(param.node, back_node, vul_function, vul_lineno)

                if isinstance(param.node, php.BinaryOp):
                    analysis_binaryop_node(param.node, back_node, vul_function, vul_lineno)

                if isinstance(param.node, php.ArrayOffset):
                    analysis_arrayoffset_node(param.node, vul_function, vul_lineno)

    except Exception as e:
        logger.debug(e)


def analysis_binaryop_node(node, back_node, vul_function, vul_lineno, function_params=None, file_path=None):
    """
    处理BinaryOp类型节点-->取出参数-->回溯判断参数是否可控-->输出结果
    :param file_path: 
    :param node:
    :param back_node:
    :param vul_function:
    :param vul_lineno:
    :param function_params:
    :return:
    """
    logger.debug('[AST] vul_function:{v}'.format(v=vul_function))
    params = get_binaryop_params(node)
    params = export_list(params, export_params=[])

    for param in params:
        param = php.Variable(param)
        param_lineno = node.lineno
        # is_co, cp, expr_lineno = parameters_back(param, back_node, function_params)

        if file_path is not None:
            # with open(file_path, 'r') as fi:
            fi = codecs.open(file_path, 'r', encoding='utf-8', errors='ignore')
            code_content = fi.read()
            is_co, cp, expr_lineno = anlysis_params(param, code_content, file_path, param_lineno,
                                                    vul_function=vul_function)
        else:
            count = 0
            is_co, cp, expr_lineno = deep_parameters_back(node, back_node, function_params, count, file_path,
                                                          vul_function=vul_function)

        set_scan_results(is_co, cp, expr_lineno, vul_function, param, vul_lineno)


def analysis_objectproperry_node(node, back_node, vul_function, vul_lineno, function_params=None, file_path=None):
    """
    处理_objectproperry类型节点-->取出参数-->回溯判断参数是否可控-->输出结果
    :param file_path: 
    :param node:
    :param back_node:
    :param vul_function:
    :param vul_lineno:
    :param function_params:
    :return:
    """
    logger.debug('[AST] vul_function:{v}'.format(v=vul_function))

    param = node
    param_lineno = node.lineno

    # is_co, cp, expr_lineno = parameters_back(param, back_node, function_params)
    if file_path is not None:
        # with open(file_path, 'r') as fi:
        fi = codecs.open(file_path, 'r', encoding='utf-8', errors='ignore')
        code_content = fi.read()

        is_co, cp, expr_lineno = anlysis_params(param, code_content, file_path, param_lineno, vul_function=vul_function)
    else:
        count = 0
        is_co, cp, expr_lineno = deep_parameters_back(node, back_node, function_params, count,
                                                      vul_function=vul_function)

    set_scan_results(is_co, cp, expr_lineno, vul_function, param, vul_lineno)


def analysis_arrayoffset_node(node, vul_function, vul_lineno):
    """
    处理ArrayOffset类型节点-->取出参数-->回溯判断参数是否可控-->输出结果
    :param node:
    :param vul_function:
    :param vul_lineno:
    :return:
    """
    logger.debug('[AST] vul_function:{v}'.format(v=vul_function))
    param = get_node_name(node.node)
    expr_lineno = node.lineno
    is_co, cp = is_controllable(param)

    set_scan_results(is_co, cp, expr_lineno, vul_function, param, vul_lineno)


def analysis_functioncall_node(node, back_node, vul_function, vul_lineno, function_params=None, file_path=None):
    """
    处理FunctionCall类型节点-->取出参数-->回溯判断参数是否可控-->输出结果
    :param file_path: 
    :param node:
    :param back_node:
    :param vul_function:
    :param vul_lineno:
    :param function_params:
    :return:
    """
    logger.debug('[AST] vul_function:{v}'.format(v=vul_function))
    params = get_all_params(node.params)
    for param in params:
        param = php.Variable(param)
        param_lineno = node.lineno
        # is_co, cp, expr_lineno = parameters_back(param, back_node, function_params)

        if file_path is not None:
            # with open(file_path, 'r') as fi:
            fi = codecs.open(file_path, 'r', encoding='utf-8', errors='ignore')
            code_content = fi.read()

            is_co, cp, expr_lineno = anlysis_params(param, code_content, file_path, param_lineno,
                                                    vul_function=vul_function)
        else:
            count = 0
            is_co, cp, expr_lineno = deep_parameters_back(node, back_node, function_params, count, file_path,
                                                          vul_function=vul_function)

        set_scan_results(is_co, cp, expr_lineno, vul_function, param, vul_lineno)


def analysis_variable_node(node, back_node, vul_function, vul_lineno, function_params=None, file_path=None):
    """
    处理Variable类型节点-->取出参数-->回溯判断参数是否可控-->输出结果
    :param file_path: 
    :param node:
    :param back_node:
    :param vul_function:
    :param vul_lineno:
    :param function_params:
    :return:
    """
    logger.debug('[AST] vul_function:{v}'.format(v=vul_function))
    param = get_node_name(node)
    param_lineno = node.lineno

    if file_path is not None:
        # with open(file_path, 'r') as fi:
        fi = codecs.open(file_path, 'r', encoding='utf-8', errors='ignore')
        code_content = fi.read()

        is_co, cp, expr_lineno = anlysis_params(param, code_content, file_path, param_lineno, vul_function=vul_function)
    else:
        count = 0
        is_co, cp, expr_lineno = deep_parameters_back(node, back_node, function_params, count, file_path,
                                                      vul_function=vul_function)

    set_scan_results(is_co, cp, expr_lineno, vul_function, param, vul_lineno)


def analysis_ternaryop_node(node, back_node, vul_function, vul_lineno, function_params=None, file_path=None,
                            repair_functions=[]):
    """
    处理三元提交判断语句，回溯双变量
    :param node: 
    :param back_node: 
    :param vul_function: 
    :param vul_lineno: 
    :param function_params: 
    :param file_path: 
    :return: 
    """
    logger.debug('[AST] vul_function:{v}'.format(v=vul_function))
    param = node.expr
    node1 = node.iftrue
    node2 = node.iffalse

    if type(node1) is int:
        node1 = php.Variable(node1)

    if type(node2) is int:
        node2 = php.Variable(node2)

    logger.debug('[AST] vul_param1: {}, vul_param2: {}'.format(node1, node2))

    count = 0
    is_co, cp, expr_lineno = deep_parameters_back(node1, back_node, function_params, count, file_path)
    set_scan_results(is_co, cp, expr_lineno, vul_function, param, vul_lineno)

    is_co, cp, expr_lineno = deep_parameters_back(node2, back_node, function_params, count, file_path)
    set_scan_results(is_co, cp, expr_lineno, vul_function, param, vul_lineno)


def analysis_if_else(node, back_node, vul_function, vul_lineno, function_params=None, file_path=None):
    nodes = []
    if isinstance(node.node, php.Block):  # if语句中的sink点以及变量
        analysis(node.node.nodes, vul_function, back_node, vul_lineno, file_path, function_params)
    else:
        analysis([node.node], vul_function, back_node, vul_lineno, file_path, function_params)

    if node.else_ is not None:  # else语句中的sink点以及变量
        if isinstance(node.else_.node, php.Block):
            analysis(node.else_.node.nodes, vul_function, back_node, vul_lineno, file_path, function_params)
        else:
            analysis([node.node], vul_function, back_node, vul_lineno, file_path, function_params)

    if len(node.elseifs) != 0:  # elseif语句中的sink点以及变量
        for i_node in node.elseifs:
            if i_node.node is not None:
                if isinstance(i_node.node, php.Block):
                    analysis(i_node.node.nodes, vul_function, back_node, vul_lineno, file_path, function_params)

                else:
                    nodes.append(i_node.node)
                    analysis(nodes, vul_function, back_node, vul_lineno, file_path, function_params)


def analysis_echo_print(node, back_node, vul_function, vul_lineno, function_params=None, file_path=None):
    """
    处理echo/print类型节点-->判断节点类型-->不同If分支回溯判断参数是否可控-->输出结果
    :param file_path: 
    :param node:
    :param back_node:
    :param vul_function:
    :param vul_lineno:
    :param function_params:
    :return:
    """
    global scan_results

    if int(vul_lineno) == int(node.lineno):
        if isinstance(node, php.Print):
            if isinstance(node.node, php.FunctionCall):
                analysis_functioncall_node(node.node, back_node, vul_function, vul_lineno, function_params,
                                           file_path=file_path)

            if isinstance(node.node, php.Variable) and vul_function == 'print':  # 直接输出变量信息
                analysis_variable_node(node.node, back_node, vul_function, vul_lineno, function_params,
                                       file_path=file_path)

            if isinstance(node.node, php.BinaryOp) and vul_function == 'print':
                analysis_binaryop_node(node.node, back_node, vul_function, vul_lineno, function_params,
                                       file_path=file_path)

            if isinstance(node.node, php.ArrayOffset) and vul_function == 'print':
                analysis_arrayoffset_node(node.node, vul_function, vul_lineno)

            if isinstance(node.node, php.TernaryOp) and vul_function == 'print':
                analysis_ternaryop_node(node.node, back_node, vul_function, vul_lineno, function_params,
                                        file_path=file_path)

        elif isinstance(node, php.Echo):
            for k_node in node.nodes:
                if isinstance(k_node, php.FunctionCall):  # 判断节点中是否有函数调用节点
                    analysis_functioncall_node(k_node, back_node, vul_function, vul_lineno, function_params,
                                               file_path=file_path)  # 将含有函数调用的节点进行分析

                if isinstance(k_node, php.Variable) and vul_function == 'echo':
                    analysis_variable_node(k_node, back_node, vul_function, vul_lineno, function_params,
                                           file_path=file_path)

                if isinstance(k_node, php.BinaryOp) and vul_function == 'echo':
                    analysis_binaryop_node(k_node, back_node, vul_function, vul_lineno, function_params,
                                           file_path=file_path)

                if isinstance(k_node, php.ArrayOffset) and vul_function == 'echo':
                    analysis_arrayoffset_node(k_node, vul_function, vul_lineno)

                if isinstance(k_node, php.TernaryOp) and vul_function == 'echo':
                    analysis_ternaryop_node(k_node, back_node, vul_function, vul_lineno, function_params,
                                            file_path=file_path)


def analysis_return(node, back_node, vul_function, vul_lineno, function_params=None, file_path=None):
    """
    处理return节点
    :param file_path: 
    :param node:
    :param back_node:
    :param vul_function:
    :param vul_lineno:
    :param function_params:
    :return:
    """
    global scan_results

    if int(vul_lineno) == int(node.lineno) and isinstance(node, php.Return):
        if isinstance(node.node, php.FunctionCall):
            analysis_functioncall_node(node.node, back_node, vul_function, vul_lineno, function_params,
                                       file_path=file_path)

        if isinstance(node.node, php.Variable):  # 直接输出变量信息
            analysis_variable_node(node.node, back_node, vul_function, vul_lineno, function_params,
                                   file_path=file_path)

        if isinstance(node.node, php.BinaryOp):
            analysis_binaryop_node(node.node, back_node, vul_function, vul_lineno, function_params,
                                   file_path=file_path)

        if isinstance(node.node, php.ArrayOffset):
            analysis_arrayoffset_node(node.node, vul_function, vul_lineno)

        if isinstance(node.node, php.TernaryOp):
            analysis_ternaryop_node(node.node, back_node, vul_function, vul_lineno, function_params,
                                    file_path=file_path)

        if isinstance(node.node, php.Silence):
            nodes = get_silence_params(node.node)
            analysis(nodes, vul_function, back_node, vul_lineno, file_path)


def analysis_eval(node, vul_function, back_node, vul_lineno, function_params=None, file_path=None):
    """
    处理eval类型节点-->判断节点类型-->不同If分支回溯判断参数是否可控-->输出结果
    :param file_path: 
    :param node:
    :param vul_function:
    :param back_node:
    :param vul_lineno:
    :param function_params:
    :return:
    """
    global scan_results

    if vul_function == 'eval' and int(node.lineno) == int(vul_lineno):
        if isinstance(node.expr, php.Variable):
            analysis_variable_node(node.expr, back_node, vul_function, vul_lineno, function_params, file_path=file_path)

        if isinstance(node.expr, php.FunctionCall):
            analysis_functioncall_node(node.expr, back_node, vul_function, vul_lineno, function_params,
                                       file_path=file_path)

        if isinstance(node.expr, php.BinaryOp):
            analysis_binaryop_node(node.expr, back_node, vul_function, vul_lineno, function_params, file_path=file_path)

        if isinstance(node.expr, php.ArrayOffset):
            analysis_arrayoffset_node(node.expr, vul_function, vul_lineno)

        if isinstance(node.expr, php.ObjectProperty):
            analysis_objectproperry_node(node.expr, back_node, vul_function, vul_lineno, function_params,
                                         file_path=file_path)

        if isinstance(node.expr, php.Silence):
            nodes = get_silence_params(node.expr)
            analysis(nodes, vul_function, back_node, vul_lineno, file_path)


def analysis_file_inclusion(node, vul_function, back_node, vul_lineno, function_params=None, file_path=None):
    """
    处理include/require类型节点-->判断节点类型-->不同If分支回溯判断参数是否可控-->输出结果
    :param file_path: 
    :param node:
    :param vul_function:
    :param back_node:
    :param vul_lineno:
    :param function_params:
    :return:
    """
    global scan_results
    include_fs = ['include', 'include_once', 'require', 'require_once']

    if vul_function in include_fs and int(node.lineno) == int(vul_lineno):
        logger.debug('[AST-INCLUDE] {l}-->{r}'.format(l=vul_function, r=vul_lineno))

        if isinstance(node.expr, php.Variable):
            analysis_variable_node(node.expr, back_node, vul_function, vul_lineno, function_params, file_path=file_path)

        if isinstance(node.expr, php.FunctionCall):
            analysis_functioncall_node(node.expr, back_node, vul_function, vul_lineno, function_params,
                                       file_path=file_path)

        if isinstance(node.expr, php.BinaryOp):
            analysis_binaryop_node(node.expr, back_node, vul_function, vul_lineno, function_params, file_path=file_path)

        if isinstance(node.expr, php.ArrayOffset):
            analysis_arrayoffset_node(node.expr, vul_function, vul_lineno)

        if isinstance(node.expr, php.ObjectProperty):
            analysis_objectproperry_node(node.expr, back_node, vul_function, vul_lineno, function_params,
                                         file_path=file_path)


def set_scan_results(is_co, cp, expr_lineno, sink, param, vul_lineno):
    """
    获取结果信息-->输出结果
    :param is_co:
    :param cp:
    :param expr_lineno:
    :param sink:
    :param param:
    :param vul_lineno:
    :return:
    """
    results = []
    global scan_results

    result = {
        'code': is_co,
        'source': cp,
        'source_lineno': expr_lineno,
        'sink': sink,
        'sink_param:': param,
        'sink_lineno': vul_lineno
    }
    if result['code'] > 0:  # 查出来漏洞结果添加到结果信息中
        results.append(result)
        scan_results += results


def analysis(nodes, vul_function, back_node, vul_lineo, file_path=None, function_params=None):
    """
    调用FunctionCall-->analysis_functioncall分析调用函数是否敏感
    :param nodes: 所有节点
    :param vul_function: 要判断的敏感函数名
    :param back_node: 各种语法结构里面的语句
    :param vul_lineo: 漏洞函数所在行号
    :param function_params: 自定义函数的所有参数列表
    :param file_path: 当前分析文件的地址
    :return:
    """
    buffer_ = []
    for node in nodes:
        if isinstance(node, php.FunctionCall):  # 函数直接调用，不进行赋值
            anlysis_function(node, back_node, vul_function, function_params, vul_lineo, file_path=file_path)

        elif isinstance(node, php.Assignment):  # 函数调用在赋值表达式中
            if isinstance(node.expr, php.FunctionCall):
                anlysis_function(node.expr, back_node, vul_function, function_params, vul_lineo, file_path=file_path)

            if isinstance(node.expr, php.Eval):
                analysis_eval(node.expr, vul_function, back_node, vul_lineo, function_params, file_path=file_path)

            if isinstance(node.expr, php.Silence):
                buffer_.append(node.expr)
                analysis(buffer_, vul_function, back_node, vul_lineo, file_path, function_params)

        elif isinstance(node, php.Return):
            analysis_return(node, back_node, vul_function, vul_lineo, function_params, file_path=file_path)

        elif isinstance(node, php.Print) or isinstance(node, php.Echo):
            analysis_echo_print(node, back_node, vul_function, vul_lineo, function_params, file_path=file_path)

        elif isinstance(node, php.Silence):
            nodes = get_silence_params(node)
            analysis(nodes, vul_function, back_node, vul_lineo, file_path)

        elif isinstance(node, php.Eval):
            analysis_eval(node, vul_function, back_node, vul_lineo, function_params, file_path=file_path)

        elif isinstance(node, php.Include) or isinstance(node, php.Require):
            analysis_file_inclusion(node, vul_function, back_node, vul_lineo, function_params, file_path=file_path)

        elif isinstance(node, php.If):  # 函数调用在if-else语句中时
            analysis_if_else(node, back_node, vul_function, vul_lineo, function_params, file_path=file_path)

        elif isinstance(node, php.While) or isinstance(node, php.For):  # 函数调用在循环中
            if isinstance(node.node, php.Block):
                analysis(node.node.nodes, vul_function, back_node, vul_lineo, file_path, function_params)

        elif isinstance(node, php.Function) or isinstance(node, php.Method):
            function_body = []
            function_params = get_function_params(node.params)

            analysis(node.nodes, vul_function, function_body, vul_lineo, function_params=function_params,
                     file_path=file_path)

        elif isinstance(node, php.Class):
            analysis(node.nodes, vul_function, back_node, vul_lineo, file_path, function_params)

        back_node.append(node)


def scan_parser(code_content, sensitive_func, vul_lineno, file_path, repair_functions=[]):
    """
    开始检测函数
    :param repair_functions: 
    :param code_content: 要检测的文件内容
    :param sensitive_func: 要检测的敏感函数,传入的为函数列表
    :param vul_lineno: 漏洞函数所在行号
    :param file_path: 文件路径
    :return:
    """
    try:
        global scan_results, is_repair_functions
        scan_results = []
        is_repair_functions = repair_functions
        parser = make_parser()
        all_nodes = parser.parse(code_content, debug=False, lexer=lexer.clone(), tracking=with_line)

        for func in sensitive_func:  # 循环判断代码中是否存在敏感函数，若存在，递归判断参数是否可控;对文件内容循环判断多次
            back_node = []
            analysis(all_nodes, func, back_node, int(vul_lineno), file_path, function_params=None)
    except SyntaxError as e:
        logger.warning('[AST] [ERROR]:{e}'.format(e=e))

    return scan_results
