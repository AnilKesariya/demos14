from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = 'account.journal'
    _description = 'Account Journal'

    place = fields.Char('Expedition place', size=128)
    serie = fields.Char(size=32)
