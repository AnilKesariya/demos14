from odoo import models, fields


class ResBank(models.Model):
    _inherit = "res.bank"
    _description = 'Partner Bank'

    code_sat = fields.Char(required=True)
