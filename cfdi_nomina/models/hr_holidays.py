
from odoo.exceptions import UserError
from odoo import models, fields, api, _


class Holidays(models.Model):
    _inherit = "hr.leave"

    def _get_default_company_id(self):
        if self.employee_id:
            return self._context.get('force_company', self.employee_id.company_id.id)
        return self._context.get('force_company', self.env.user.company_id.id)

    company_id = fields.Many2one(
        'res.company', string='Company', default=_get_default_company_id)
    
    # Campo existente ahora en readonly
    payslip_status = fields.Boolean(readonly=True)
    afecta_imss = fields.Selection([
        ('incapacidad', 'Incapacidad'),
        ('ausentismo', 'Ausentismo'),
    ], related="holiday_status_id.afecta_imss", string="IMSS Affection", readonly=True,
        states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]})
    cert_incapacidad_imss = fields.Char('Certificado IMSS', readonly=True,
                                        states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]})
    tipo_incapacidad_imss = fields.Selection([
        ('01', '01-Riesgo de trabajo'),
        ('02', '02-Enfermedad en general'),
        ('03', '03-Maternidad'),
    ], readonly=True, states={'draft': [('readonly', False)], 'confirm': [('readonly', False)]})

    retardo_parent_id = fields.Many2one('hr.leave', ondelete="set null")
    retardos_acum_list = fields.One2many(
        'hr.leave', 'retardo_parent_id', string='Accumulated delays', readonly=True)

    @api.model
    def create(self, vals):
        # obtiene la company del empleado
        if vals.get('employee_id'):
            employee = self.env['hr.employee'].sudo().browse(vals[
                'employee_id'])
            if employee.company_id:
                vals['company_id'] = employee.company_id.id
        return super(Holidays, self).create(vals)

    def action_refuse(self):
        res = super(Holidays, self).action_refuse()
        for holiday in self:
            if holiday.retardos_acum_list:
                ultimo_retardo = holiday.retardos_acum_list[0]
                ultimo_retardo.retardo_parent_id = False
                ultimo_retardo.action_refuse()

                holiday.retardos_acum_list.write({'payslip_status': False})
                holiday.retardos_acum_list.write({'retardo_parent_id': False})

            if holiday.retardo_parent_id and holiday.retardo_parent_id.state in ['confirm', 'validate', 'validate1']:
                raise UserError(_('Este retardo esta asociado a una falta confirmada. Rechace primero la Falta [%s]') %
                                holiday.retardo_parent_id.name)

        self.write({'payslip_status': False})

        return res


class HrHolidaysStatus(models.Model):
    _inherit = "hr.leave.type"

    fdia_7 = fields.Boolean("Seventh day", default=False,
                            help='Check if affected')
    fdias_ptu = fields.Boolean(
        "Days worked for PTU", default=False, help='Check if affected')
    fdias_infonavit = fields.Boolean(
        "Days worked for INFONAVIT", default=False, help='Check if affected')
    afecta_imss = fields.Selection([
        ('incapacidad', 'Incapacidad'),
        ('ausentismo', 'Ausentismo'),
    ], string="IMSS", help='Select the type of affectation. Leave blank if not applicable')
