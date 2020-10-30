from odoo import api, models, fields


class BatchCfdi(models.TransientModel):
    _name = "cfdi_nomina.batch.cfdi"
    _description = 'BatchCfdi'

    fecha_pago = fields.Date()
    nominas = fields.Many2many("hr.payslip", required=True)
    concepto = fields.Char()

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._context.get("active_model") == 'hr.payslip.run':
            run = self.env["hr.payslip.run"].browse(
                self._context.get("active_id"))
            res["nominas"] = run.slip_ids.ids
            res["concepto"] = run.name
            res["fecha_pago"] = run.fecha_pago
        return res

    def action_batch_cfdi(self):
        if self.fecha_pago:
            self.nominas.write({
                'concepto': self.concepto,
                'fecha_pago': self.fecha_pago
            })
        self.nominas.action_create_cfdi()
        return True
