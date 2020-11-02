# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from datetime import timedelta
import datetime
import base64
from lxml import etree
from lxml.objectify import fromstring
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)
try:
    import xmltodict
except ImportError:
    _logger.debug('Can not import xmltodict.')


class PaySlipReport(models.AbstractModel):
    _name = 'report.cfdi_nomina.nomina_report'


    comprobante = fields.Char(string="coprobante")
    timbre = fields.Char(string="Timbre")
    total_especie = fields.Float(string="Total Especie")
    total_p = fields.Float(string="Total P")
    total_d = fields.Float(string="Total D")
    total_o = fields.Float(string="Total O")
    lines_d = fields.Char(string="lines d")
    lines_o = fields.Char(string="lines o")


    def get_nomina_data(self, o, dato, default=''):
        nomina = self.comprobante[o.id].get('cfdi:Complemento', {}).get('nomina12:Nomina', {})
        valor = nomina.get('@{}'.format(dato), default)
        return valor

    def get_comprobante_data(self, o, campo, default=''):
        valor = self.comprobante[o.id].get('@{}'.format(campo), default)
        return valor

    def get_timbre_data(self, o, campo, default=''):
        valor = self.timbre[o.id].get(campo, default)
        return valor

    def get_faltas(self, o):
        faltas_list = o.worked_days_line_ids.mapped('holiday_ids').filtered(
            lambda inc: inc.afecta_imss == 'ausentismo')
        return len(faltas_list)

    def get_company_name(self, o):
        nombre = o.company_id.parent_id.name if o.company_id.parent_id else o.company_id.name
        return nombre

    def get_dias_trabajados(self, o):
        worked_line = o.worked_days_line_ids.filtered(lambda l: l.code == 'WORK100')
        if not worked_line:
            return 0
        return worked_line.number_of_days

    def get_total_percepciones(self, o):
        return self.total_p

    def get_otros_pagos_lines(self, o):
        return self.lines_o

    def get_total_deducciones(self, o):
        return self.total_d

    def get_total_otros(self, o):
        return self.total_o

    def get_total_neto(self, o):
        return self.total_p + self.total_o - self.total_d

    def get_total_efectivo(self, o):
        return self.total_p + self.total_o - self.total_especie - self.total_d

    def get_deducciones_lines(self, o):
        return self.lines_d

    def get_percepciones_lines(self, o):
        p_id = self.env.ref("cfdi_nomina.catalogo_tipo_percepcion").id
        d_id = self.env.ref("cfdi_nomina.catalogo_tipo_deduccion").id
        o_id = self.env.ref("cfdi_nomina.catalogo_tipo_otro_pago").id

        self.total_especie = 0
        total_p = 0
        total_d = 0
        total_o = 0
        lines_p = []
        lines_d = []
        lines_o = []
        for line in o.line_ids:
            if not line.appears_on_payslip or not line.total:
                continue
            if line.salary_rule_id.tipo_id.id == p_id:
                total_p += line.total
                lines_p.append({
                    'code': line.code,
                    'name': line.name,
                    'total': line.total,
                })
            if line.salary_rule_id.tipo_id.id == d_id:
                # ISR Negativo se va a Otros Pagos, pero sigue apareciendo en deducciones

                if line.code == 'D001' and line.total < 0:
                    total_o += abs(line.total)

                total_d += line.total
                lines_d.append({
                    'code': line.code,
                    'name': line.name,
                    'total': line.total,
                })
            if line.salary_rule_id.tipo_id.id == o_id:
                if line.code == 'D100':   # SUBSIDIO PARA EL EMPLEO':
                    # Subsidio se pasa en negativo en el lado de deducciones
                    total_d -= line.total
                    lines_d.append({
                        'code': line.code,
                        'name': line.name,
                        'total': -line.total,
                    })
                    continue
                total_o += line.total
                lines_o.append({
                    'code': line.code,
                    'name': line.name,
                    'total': line.total,
                })

            if line.salary_rule_id.en_especie:
                self.total_especie += line.total

        self.total_p = total_p
        self.total_d = total_d
        self.total_o = total_o

        self.lines_d = lines_d
        self.lines_o = lines_o

        return lines_p

    def get_xmldata(self, docids):
        self.comprobante = {}
        self.timbre = {}
        for doc_id in docids:
            self.timbre[doc_id] = {}
            self.comprobante[doc_id] = {}
            attach_row = self.env['ir.attachment'].search([('res_id', '=', doc_id),
                                                           ('res_model', '=', 'hr.payslip')])
            for atta in attach_row:
                if 'xml' in atta.mimetype or 'text' in atta.mimetype:
                    tree = fromstring(base64.decodebytes(atta.datas))
                    attribute = 'tfd:TimbreFiscalDigital[1]'
                    namespace = {'tfd': 'http://www.sat.gob.mx/TimbreFiscalDigital'}
                    node = tree.Complemento.xpath(attribute, namespaces=namespace)
                    self.timbre[doc_id] = node[0] if node else None
                    self.comprobante[doc_id] = dict(xmltodict.parse(base64.decodebytes(atta.datas)).get('cfdi:Comprobante', {}))
                    break
        return

    @api.model
    def _get_report_values(self, docids, data=None):
        payslips = self.env['hr.payslip'].browse(docids)
        self.get_xmldata(docids)
        return {
            'doc_ids': docids,
            'doc_model': 'hr.payslip',
            'docs': payslips,
            'data': data,
            'get_company_name': self.get_company_name,
            'get_faltas': self.get_faltas,
            'get_dias_trabajados': self.get_dias_trabajados,
            'get_percepciones_lines': self.get_percepciones_lines,
            'get_otros_pagos_lines': self.get_otros_pagos_lines,
            'get_deducciones_lines': self.get_deducciones_lines,
            'get_total_percepciones': self.get_total_percepciones,
            'get_total_deducciones': self.get_total_deducciones,
            'get_total_otros': self.get_total_otros,
            'get_total_neto': self.get_total_neto,
            'get_total_efectivo': self.get_total_efectivo,
            'nomina_data': self.get_nomina_data,
            'timbre_data': self.get_timbre_data,
            'comprobante_data': self.get_comprobante_data,
            'float': float,
        }

