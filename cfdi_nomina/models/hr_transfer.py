from odoo.exceptions import ValidationError, UserError
import datetime


from odoo import api, models, fields


class HrEmployeeTransfer(models.Model):
    _name = "hr.employee.transfer"
    _rec_name = 'date'
    _description = 'Employee transfers'

    date = fields.Date('Date', required=True, default=datetime.datetime.now())
    employee_id = fields.Many2one('hr.employee', string='Employee', required=True)
    company_id = fields.Many2one('res.company', string='Origin Warehouse', readonly=True)
    company_dest_id = fields.Many2one('res.company', string='Destination Warehouse', readonly=True)
    wage = fields.Float('Daily Salary')