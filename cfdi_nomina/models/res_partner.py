from odoo import models, fields


class partner(models.Model):
    _inherit = "res.partner"
    _description = 'Partner'

    is_employee = fields.Boolean('IS Employee')
    # rfc = fields.Char(string="RFC")
