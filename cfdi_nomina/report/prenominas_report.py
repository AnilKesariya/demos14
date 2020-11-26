# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
import logging
_logger = logging.getLogger(__name__)

tipo_cuenta_dict = {
    '01': '01 Efectivo',
    '02': '02 Cheque nominativo',
    '03': '03 Transferencia electrónica de fondos',
}


class NominasReport(models.AbstractModel):
    _name = 'report.cfdi_nomina.reporte_prenominas'

    total_p = fields.Float(string="Total P")
    total_isr = fields.Float(string="Total Isr")
    total_gravable = fields.Float(string="Total Taxable")
    lines_p = fields.Char(string="lines P")
    lines_d = fields.Char(string="lines D")
    lines_o = fields.Char(string="Others")
    otras_p = fields.Char(string="Others P")
    otras_d = fields.Char(string="Others D")
    total_subsidio_empleo = fields.Float(string="Total employment subsidy")
    dias_trabajados = fields.Float(string="Days Worked")
    horas_trabajados = fields.Float(string="Hours Worked")
    salarioXhora = fields.Float(string="Hourly Wage")
    total_sueldo = fields.Float(string="Total Salary")
    total_d = fields.Float(string="Total D")
    total_o = fields.Float(string="Total O")
    total_imss = fields.Float(string="Total IMSS")
    total_especie = fields.Float(string="Total Species")
    t_efectivo = fields.Float(string="T Effective")
    t_neto = fields.Float(string="T Net")
    t_especie = fields.Float(string="T Species")
    t_gravable = fields.Float(string="T Taxable")
    t_subsidio = fields.Float(string="T Grant")
    total_lines_p = fields.Char(string="Total lines P")
    total_lines_o = fields.Char(string="Total Lines O")
    total_lines_d = fields.Char(string="Total lines D")
    totales = fields.Float(string="Total FDP")

    def calc_reglas_lines(self, o):
        p_id = self.env.ref("cfdi_nomina.catalogo_tipo_percepcion").id
        d_id = self.env.ref("cfdi_nomina.catalogo_tipo_deduccion").id
        o_id = self.env.ref("cfdi_nomina.catalogo_tipo_otro_pago").id

        self.total_p = self.total_d = self.total_o = self.total_sueldo = 0
        self.total_isr = self.total_imss = self.total_subsidio_empleo = self.total_especie = 0
        self.total_gravable = 0

        lines_p = []
        lines_d = []
        lines_o = []
        for line in o.line_ids:
            if not line.appears_on_payslip or not line.total:
                continue

            if line.salary_rule_id.tipo_id.id == p_id:
                self.total_p += line.total
                self.total_gravable += line.gravado

                if line.code == 'P001':   # SUELDO':
                    self.total_sueldo += line.total
                lines_p.append({
                    'code': line.code,
                    'name': line.name,
                    'total': line.total,
                })

            if line.salary_rule_id.tipo_id.id == d_id:
                self.total_d += line.total
                if line.code == 'D001':  # 'ISR':
                    self.total_isr += line.total
                if line.code == 'D002':  # 'IMSS':
                    self.total_imss += line.total

                lines_d.append({
                    'code': line.code,
                    'name': line.name,
                    'total': line.total,
                })

            if line.salary_rule_id.tipo_id.id == o_id:
                if line.code == 'D100':   # SUBSIDIO PARA EL EMPLEO':
                    # Subsidio se pasa en negativo en el lado de deducciones
                    self.total_subsidio_empleo -= line.total
                    self.total_d -= line.total
                    lines_d.append({
                        'code': line.code,
                        'name': line.name,
                        'total': -line.total,
                    })
                    continue
                self.total_o += line.total
                # _logger.info("T.Otros {}, codigo:{}, {}".format(self.total_o, line.code, line.total))
                lines_o.append({
                    'code': line.code,
                    'name': line.name,
                    'total': line.total,
                })

            if line.salary_rule_id.en_especie:
                self.total_especie += line.total

        self.lines_p = lines_p
        self.lines_d = lines_d
        self.lines_o = lines_o

        self.otras_p = self.total_p - self.total_sueldo
        self.otras_d = self.total_d - self.total_isr - self.total_imss - self.total_subsidio_empleo
        self.total_subsidio_empleo *= -1

        data_trabajados = o.worked_days_line_ids.filtered(lambda l: l.code == 'WORK100')
        self.dias_trabajados = sum(data_trabajados.mapped('number_of_days'))
        self.horas_trabajados = sum(data_trabajados.mapped('number_of_hours'))
        self.salarioXhora = self.total_sueldo/self.horas_trabajados if self.horas_trabajados else 0

        # Acumula lineas totales
        for l in self.lines_p:
            code = l.get('code')
            if code in self.total_lines_p:
                self.total_lines_p[code]['total'] += l.get('total', 0)
            else:
                self.total_lines_p[code] = l

        for l in self.lines_o:
            code = l.get('code')
            if code in self.total_lines_o:
                self.total_lines_o[code]['total'] += l.get('total', 0)
            else:
                self.total_lines_o[code] = l

        for l in self.lines_d:
            code = l.get('code')
            if code in self.total_lines_d:
                self.total_lines_d[code]['total'] += l.get('total', 0)
            else:
                self.total_lines_d[code] = l

        # Acumula totales

        self.t_efectivo += self.total_p + self.total_o - self.total_especie - self.total_d
        self.t_neto += self.total_p + self.total_o - self.total_d
        # _logger.info("total P {} + Total O {} - Total D {}".format(self.total_p, self.total_o, self.total_d))
        self.t_especie += self.total_especie
        self.t_gravable += self.total_gravable
        self.t_subsidio += self.total_subsidio_empleo

        # Acumula total efectivo por Forma de Pago
        fdp = o.employee_id.tipo_cuenta
        if fdp in self.totales:
            self.totales[fdp]['t_efectivo'] += self.total_p + self.total_o - self.total_especie - self.total_d
        else:
            self.totales[fdp] = {
                'fdp': tipo_cuenta_dict[fdp],
                't_efectivo':  self.total_p + self.total_o - self.total_especie - self.total_d,
            }
        return self

    def get_total(self, o):
        return self

    def get_totales(self):
        return [v for k, v in self.totales.items()]

    def get_totales_percepciones(self):
        return [v for k, v in self.total_lines_p.items()]

    def get_totales_otros(self):
        return [v for k, v in self.total_lines_o.items()]
    
    def get_totales_deducciones(self):
        return [v for k, v in self.total_lines_d.items()]

    def get_dato_acumulado(self, o, nombre):
        dato = o.acumulado_ids.filtered(lambda l: l.name == nombre)
        dato = dato and dato.actual_nc or 0.0
        return '{:,.2f}'.format(dato)

    @api.model
    def _get_report_values(self, docids, data=None):
        run_id = self._context.get('active_id')
        pay_run = self.env['hr.payslip.run'].browse(run_id)
        payslips = self.env['hr.payslip'].browse(data.get('payslip_ids', []))
        data.update(payslips=payslips)
        self.total_lines_p = {}
        self.total_lines_o = {}
        self.total_lines_d = {}
        self.totales = {}
        self.t_neto = 0
        self.t_especie = 0
        self.t_gravable = 0
        self.t_subsidio = 0
        self.t_efectivo = 0

        return {
            'doc_ids': [run_id],
            'doc_model': 'hr.payslip.run',
            'docs': [pay_run],
            'data': data,
            'float': float,
            'calc_reglas_lines': self.calc_reglas_lines,
            'get_dato_acumulado': self.get_dato_acumulado,
            'get_totales_percepciones': self.get_totales_percepciones,
            'get_totales_deducciones': self.get_totales_deducciones,
            'get_totales_otros': self.get_totales_otros,
            'get_totales': self.get_totales,
            'get_total': self.get_total,
        }

