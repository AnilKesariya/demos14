from odoo import fields, models


class HrOtherInputs(models.Model):
    _name = 'hr.other.inputs'
    _description = 'hr other inputs'
    _rec_name = 'employee_id'
    
    employee_id = fields.Many2one(
        'hr.employee', help='Employee that use this input')
    python_code = fields.Text(help='Code defined to calculate the amount')
    apply_with = fields.Selection([
        ('always', 'Always'),
        ('times', 'Times'),
        ('limit', 'Limit')])
    detail = fields.Float(
        help='If this record apply with "Times" set how many times, if apply '
        'with limit set the money to cover with the record')
    rest = fields.Float(
        help='When apply with a limit, save the rest to apply in the record')
    active = fields.Boolean()
