# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from ast import literal_eval


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'
    _description = 'Res Config Settings'

    nomina_year_days = fields.Float('Days per year', default=365)
    nomina_sf = fields.Float('Minimum wage DF')
    nomina_uma = fields.Float('UMA', help='Unit of Measurement and Update')

    attendance_range = fields.Float('Attendance Check Range',
                                    help='Minutes to look for attendance checks around the schedule')
    attendance_nretardos = fields.Integer('Number of retarods',
                                          help='Number of delays to be set as a fault')
    nomina_journal = fields.Many2one(
        'account.journal', 'Payroll Journal', required=True)

    ispt_mensual_id = fields.Many2one('hr.ispt', 'Monthly ISPT table')
    ispt_anual_id = fields.Many2one('hr.ispt', 'Annual ISPT table')
    sube_id = fields.Many2one('hr.employment.sube', 'Table of employment subsidies')

    @api.model
    def get_values(self):
        res = super(ResConfigSettings, self).get_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        nomina_year_days = float(literal_eval(
            ICPSudo.get_param('cfdi_nomina.DA', default='365')))
        nomina_sf = float(literal_eval(
            ICPSudo.get_param('cfdi_nomina.SF', default='0')))
        nomina_uma = float(literal_eval(
            ICPSudo.get_param('cfdi_nomina.UMA', default='0')))

        attendance_range = float(literal_eval(ICPSudo.get_param(
            'cfdi_nomina.AttendanceRange', default='30')))
        attendance_nretardos = int(literal_eval(
            ICPSudo.get_param('cfdi_nomina.AttendanceNDelay', default='3')))
        nomina_journal_id = int(literal_eval(ICPSudo.get_param(
            'cfdi_nomina.NominaJournalID', default='0')))

        ispt_mensual_id = int(literal_eval(ICPSudo.get_param(
            'cfdi_nomina.NominaIPSTMensualID', default='0')))
        ispt_anual_id = int(literal_eval(ICPSudo.get_param(
            'cfdi_nomina.NominaIPSTAnualID', default='0')))
        sube_id = int(literal_eval(ICPSudo.get_param(
            'cfdi_nomina.NominaSUBEID', default='0')))

        res.update(
            nomina_year_days=nomina_year_days,
            nomina_sf=nomina_sf,
            nomina_uma=nomina_uma,
            attendance_range=attendance_range,
            attendance_nretardos=attendance_nretardos,
            nomina_journal=nomina_journal_id,
            ispt_mensual_id=ispt_mensual_id,
            ispt_anual_id=ispt_anual_id,
            sube_id=sube_id,
        )
        return res

    def set_values(self):
        super(ResConfigSettings, self).set_values()
        ICPSudo = self.env['ir.config_parameter'].sudo()
        ICPSudo.set_param("cfdi_nomina.DA", str(self.nomina_year_days))
        ICPSudo.set_param("cfdi_nomina.SF", str(self.nomina_sf))
        ICPSudo.set_param("cfdi_nomina.UMA", str(self.nomina_uma))
        ICPSudo.set_param("cfdi_nomina.AttendanceRange",
                          str(self.attendance_range))
        ICPSudo.set_param("cfdi_nomina.AttendanceNDelay",
                          str(self.attendance_nretardos))
        ICPSudo.set_param("cfdi_nomina.NominaJournalID",
                          str(self.nomina_journal.id))
        ICPSudo.set_param("cfdi_nomina.NominaIPSTMensualID",
                          str(self.ispt_mensual_id.id))
        ICPSudo.set_param("cfdi_nomina.NominaIPSTAnualID",
                          str(self.ispt_anual_id.id))
        ICPSudo.set_param("cfdi_nomina.NominaSUBEID", str(self.sube_id.id))
