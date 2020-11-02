#!/usr/bin/python
# -*- coding: utf-8 -*-
import xmlrpclib
import sys
import traceback

host = "http://localhost:8069"
login = "admin"
password = "kI2hgd782gaGG"

def timbrar(res_id, db):
    sock_common = xmlrpclib.ServerProxy(host + '/xmlrpc/common')
    uid = sock_common.login(db, login, password)
    sock = xmlrpclib.ServerProxy(host + '/xmlrpc/object')
    try:
        res = sock.execute(db, uid, password, "hr.payslip", 'action_create_cfdi', [res_id])
    except xmlrpclib.Fault as ex:
        res = sock.execute(db, uid, password, "hr.payslip", 'write', [res_id], {'error_timbrado': ex.faultCode, 'estado_timbrado': 'error'})

if __name__ == '__main__':
    res_id = int(sys.argv[1])
    db = sys.argv[2]
    timbrar(res_id, db)
