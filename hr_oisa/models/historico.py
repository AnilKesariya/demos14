# -*- coding: utf-8 -*-
##############################################################################
#
#    AtharvERP Business Solutions
#    Copyright (C) 2020-TODAY AtharvERP Business Solutions(<http://www.atharverp.com>).
#    Author: AtharvERP Business Solutions(<http://www.atharverp.com>)
#    you can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    It is forbidden to publish, distribute, sublicense, or sell copies
#    of the Software or modified copies of the Software.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    GENERAL PUBLIC LICENSE (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
from odoo import models, fields
from datetime import date


class historico_sueldo(models.Model):
    _name = "hr.employee.historico.sueldo"

    name = fields.Date("Date")
    sueldo_old = fields.Float("Previous salary")
    sueldo_new = fields.Float("New salary")
    employee_id = fields.Many2one("hr.employee", string="Employee")
    user_id = fields.Many2one("res.users", string="Modified by")


class historico_otros(models.Model):
    _name = "hr.employee.historico.otros"

    name = fields.Date("Date")
    tipo = fields.Char("Type")
    valor_old = fields.Char("Previous Value")
    valor_new = fields.Char("New value")
    employee_id = fields.Many2one("hr.employee", string="Employee")
    user_id = fields.Many2one("res.users", string="Modified By")


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    historico_sueldo = fields.One2many(
        "hr.employee.historico.sueldo", "employee_id")
    historico_otros = fields.One2many(
        "hr.employee.historico.otros", "employee_id")

    def write(self, vals):
        historico1 = self.env["hr.employee.historico.sueldo"]
        historico2 = self.env["hr.employee.historico.otros"]
        for rec in self:
            if 'sueldo_diario' in vals:
                historico1.create({
                    'name': date.today(),
                    'sueldo_old': rec.sueldo_diario,
                    'sueldo_new': vals['sueldo_diario'],
                    'employee_id': rec.id,
                    'user_id': self.env.user.id,
                })
            if 'department_id' in vals:
                historico2.create({
                    'name': date.today(),
                    'tipo': 'Departamento',
                    'valor_old': rec.department_id.name,
                    'valor_new': self.env["hr.department"].browse(
                        vals["department_id"]).name,
                    'employee_id': rec.id,
                    'user_id': self.env.user.id,
                })
            if 'job_id' in vals:
                historico2.create({
                    'name': date.today(),
                    'tipo': 'Puesto',
                    'valor_old': rec.job_id.name,
                    'valor_new': self.env["hr.job"].browse(
                        vals["job_id"]).name,
                    'employee_id': rec.id,
                    'user_id': self.env.user.id,
                })
        return super().write(vals)
