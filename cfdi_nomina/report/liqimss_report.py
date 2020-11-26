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


class LiqIMSSReport(models.AbstractModel):
    _name = 'report.cfdi_nomina.reporte_liqimss'

    t_sdi = fields.Float(string="SDI Diary salary integrated")
    t_inc = fields.Float(string="Inc. Disabilities")
    t_aus = fields.Float(string="Off. Ausentismo")
    t_pe = fields.Float(string="C.F. Fixed fee")
    t_ae3 = fields.Float(string="Surplus 3 SMGDF")
    t_ed = fields.Float(string="Exc. Cash benefits")
    t_gmp = fields.Float(string="G.M.P. Medical expenses for pensioners")
    t_rt = fields.Integer(string="R.T. Occupational risk")
    t_iv = fields.Float(string="I.V. Disability and life")
    t_gua = fields.Float(string="G.P.S. Nurseries and social benefits")
    t_total = fields.Float(string="Total")
    suma_patron = fields.Float(string="Standard fee")
    suma_trab = fields.Float(string="Worker's fee")
    dias_trabajados = fields.Float(string="Days")
    aus = fields.Float(string="Off. Ausentismo")
    inc = fields.Float(string="Disabilities")

    def calc_val(self, o):

        self.suma_patron = o.pe_patron + o.ae3_patron + o.ed_patron + o.gmp_patron + o.rt_patron + o.iv_patron + \
            o.gua_patron
        self.suma_trab = o.ae3_trab + o.ed_trab + o.gmp_trab + o.iv_trab
        data_trabajados = o.worked_days_line_ids.filtered(
            lambda l: l.code == 'WORK100')
        self.dias_trabajados = sum(data_trabajados.mapped('number_of_days'))
        self.aus, self.inc = self.get_ausentismo_incapacidad(o)

        # Acumula totales
        self.t_sdi += o.sdi
        self.t_inc += self.inc
        self.t_aus += self.aus

        self.t_pe += o.pe_patron
        self.t_ae3 += o.ae3_patron + o.ae3_trab
        self.t_ed += o.ed_patron + o.ed_trab
        self.t_gmp += o.gmp_patron + o.gmp_trab
        self.t_rt += o.rt_patron
        self.t_iv += o.iv_patron + o.iv_trab
        self.t_rt += o.rt_patron
        self.t_gua += o.gua_patron
        self.t_total += self.suma_patron + self.suma_trab

        return self

    def get_total(self, o):
        return self

    def get_ausentismo_incapacidad(self, o):
        aus = inc = 0
        for line in o.worked_days_line_ids.filtered(lambda l: l.code != "WORK100"):
            line.calc_dias_imss()  # JGO  un rato
            aus += line.dias_imss_ausencia
            inc += line.dias_imss_incapacidad

        return aus, inc

    @api.model
    def _get_report_values(self, docids, data=None):
        run_id = self._context.get('active_id')
        pay_run = self.env['hr.payslip.run'].browse(run_id)
        payslips = self.env['hr.payslip'].browse(data.get('payslip_ids', []))
        data.update(payslips=payslips)

        self.t_sdi = 0
        self.t_inc = 0
        self.t_aus = 0

        self.t_pe = 0
        self.t_ae3 = 0
        self.t_ed = 0
        self.t_gmp = 0
        self.t_rt = 0
        self.t_iv = 0
        self.t_rt = 0
        self.t_gua = 0
        self.t_total = 0

        return {
            'doc_ids': [run_id],
            'doc_model': 'hr.payslip.run',
            'docs': [pay_run],
            'data': data,
            'float': float,
            'calc_val': self.calc_val,
            'get_total': self.get_total,
        }
