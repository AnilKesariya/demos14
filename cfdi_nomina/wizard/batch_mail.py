from odoo import models, fields


class batch_mail(models.TransientModel):
    _name = "cfdi_nomina.batch.mail"
    _description = 'Batch Mail'

    nominas = fields.Many2many("hr.payslip", required=True, string=u"Payroll")

    def action_batch_mail(self):
        for nomina in self.nominas:
            nomina.send_mail()
        return
