from odoo import fields, models


class HrRuleInput(models.Model):
    _name = 'hr.rule.input'
    _description = 'Salary Rule Input'

    name = fields.Char(string='Description', required=True)
    code = fields.Char(
        required=True, help="The code that can be used in the salary rules")
    input_id = fields.Many2one(
        'hr.salary.rule', string='Salary Rule Input', required=True)
    amount_python_compute = fields.Text('Formula')


class ContractType(models.Model):

    _name = 'hr.contract.type'
    _description = "Tipo Contrato"
    _order = 'sequence, id'

    name = fields.Char(string='Contract Type', required=True)
    sequence = fields.Integer(
        help="Gives the sequence when displaying a list of Contract.", default=10)
    code = fields.Char(u"Catalog code SAT", required=True)


class Contract(models.Model):

    _inherit = 'hr.contract'
    _description = 'Contract'

    type_id = fields.Many2one('hr.contract.type',string='Contract type')

    # type_id = fields.Many2one(
        # 'hr.contract.type', string='Contract Type',required=True,
        # default=lambda self: self.env['hr.contract.type'].search([], limit=1))


        