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

seleccion1 = [(str(x), str(x)) for x in range(28, 44 + 1)]
seleccion2 = [(str(x), str(x)) for x in range(22, 31 + 1)]
seleccion3 = [('CH', 'CH Chica'), ('M', 'M Mediana'),
              ('G', 'G Grande'), ('EG', 'EG Extra grande')]


class Children(models.Model):
    _name = "hr.employee.hijos"
    _description = 'hr employee children'

    nombre = fields.Char(required=True)
    edad = fields.Integer(required=True)
    nombre_padre = fields.Char("Parent's name")
    employee_id = fields.Many2one("hr.employee", string="Employee")


class EmployeeFamily(models.Model):
    _name = "hr.employee.familiar"
    _description = 'hr employee family'

    name = fields.Char("Name(s)", required=True)
    appat = fields.Char("Father's surname", required=True)
    apmat = fields.Char("Mother's surname", required=True)
    employee_id = fields.Many2one("hr.employee", string="Employee")


class EmployeePension(models.Model):
    _name = "hr.employee.pension"
    _description = 'hr employee pension'

    name = fields.Char(required=True)
    porcentaje = fields.Float(required=True)
    employee_id = fields.Many2one("hr.employee", string="Employee")
    no_card = fields.Char('No. Card', required=True)
    data_start_ret = fields.Date('Start date withholding', required=True)
    amount = fields.Char(required=True)


class EmployeeCredit(models.Model):
    _name = "hr.employee.credito"
    _description = 'hr employee credit'

    name = fields.Char(required=True)
    employee_id = fields.Many2one("hr.employee", string="Employee")


class ActaAdministrativa(models.Model):
    _name = "hr.employee.actas"
    _description = 'hr employee actas'
    _rec_name = 'fecha'

    fecha = fields.Date(required=True)
    motivo = fields.Text(required=True)
    repercusion = fields.Text(required=True)
    accion = fields.Text(required=True)
    employee_ids = fields.Many2many(
        "hr.employee", string="Employees", required=True)


class InsuranceBeneficiaries(models.Model):
    _name = "hr.employee.beneficiario_seguro"
    _description = 'hr employee insurance beneficiaries'

    name = fields.Char()
    parentesco = fields.Selection([
        ('padre', 'Father'),
        ('madre', 'Mother'),
        ('pareja', 'Couple'),
        ('hijo', 'Child(a)'),
        ('otro', 'Other')],string="Relationship")
    fecha_nacimiento = fields.Date()
    porcentaje = fields.Float()
    employee_id = fields.Many2one("hr.employee", string="Employee")


class Employee(models.Model):
    _inherit = 'hr.employee'

    talla_pantalon = fields.Selection(seleccion1, string=u"Pants")
    talla_bata = fields.Selection(seleccion1, string=u"Robe")
    talla_zapato = fields.Selection(seleccion2, string=u"Shoe/Boot")
    talla_playera = fields.Selection(seleccion3, string=u"T-shirt")
    talla_faja = fields.Selection(seleccion3, string=u"Girdle")
    documento_baja = fields.Binary(string="Low Document")
    motivo_baja = fields.Many2one('reason.low',string="Reason Low")
    offspring = fields.One2many(
        "hr.employee.hijos", "employee_id", string="Children")
    marital = fields.Selection([
        ('single', 'Single'),
        ('married', 'Married'),
        ('widower', 'Widower'),
        ('divorced', 'Divorced'),
        ('libre', 'Free union'),
        ('mop_soltero','Single Mother/Father')], 'Marital Status')
    familiares = fields.One2many("hr.employee.familiar", "employee_id")
    pensiones = fields.One2many(
        "hr.employee.pension", "employee_id", string="Alimony")
    spouse = fields.Char("Name of spouse or cohabitant")
    tipo_sangre = fields.Selection([
        ('O-', 'O-'),
        ('O+', 'O+'),
        ('A-', 'A-'),
        ('A+', 'A+'),
        ('B-', 'B-'),
        ('B+', 'B+'),
        ('AB-', 'AB-'),
        ('AB+', 'AB+'), ])
    creditos = fields.One2many(
        "hr.employee.credito", "employee_id")
    antecedentes_penales = fields.Boolean("Criminal Record")
    poliza_seguro = fields.Char("Policy")
    beneficiarios_seguro = fields.One2many(
        "hr.employee.beneficiario_seguro", "employee_id")
    actas_adm = fields.Many2many(
        "hr.employee.actas", domain=lambda self: [('employee_ids', 'in', self.env['hr.employee'].search([]).ids)], string="Administrative records", method=True)


class BeneficiarioCuenta(models.Model):
    _name = "hr.employee.beneficiario_cuenta"

    name = fields.Char(string="Name")
    direccion = fields.Text(string="Address")
    fecha_nacimiento = fields.Date("Date of birth")
    porcentaje = fields.Float(string="Percentage")
    partner_bank_id = fields.Many2one("res.partner.bank", string="Cuenta")


class ResPartnerBank(models.Model):
    _inherit = "res.partner.bank"

    beneficiarios = fields.One2many(
        "hr.employee.beneficiario_cuenta", "partner_bank_id")


class ReasonLow(models.Model):
    _name = 'reason.low'

    name = fields.Char(string="Name")