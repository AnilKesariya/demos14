# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _


class HrAttendance(models.Model):
    _inherit = "hr.attendance"

    def _get_default_company_id(self):
        if self.employee_id:
            return self._context.get('force_company', self.employee_id.company_id.id)
        return self._context.get('force_company', self.env.user.company_id.id)

    company_id = fields.Many2one(
        'res.company', string='Company', default=_get_default_company_id)

    @api.model
    def create(self, vals):
        # obtiene la company del empleado
        if vals.get('employee_id'):
            employee = self.env['hr.employee'].sudo().browse(vals['employee_id'])
            if employee.company_id:
                vals['company_id'] = employee.company_id.id
        return super(HrAttendance, self).create(vals)
