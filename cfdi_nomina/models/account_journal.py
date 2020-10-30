from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = 'account.journal'
    _description = 'Account Journal'

    lugar = fields.Char('Lugar de expedición', size=128)
    serie = fields.Char(size=32)
