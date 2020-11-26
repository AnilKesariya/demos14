import logging
from odoo.exceptions import ValidationError, UserError

from odoo import api, models, fields

_logger = logging.getLogger(__name__)


class HrRepNominasWiz(models.TransientModel):
    _name = 'hr.reporte.nominas.wiz'
    _description = 'Wizard for Generating Payroll Reports'

    company_ids = fields.Many2many('res.company', string='Companies')
    department_ids = fields.Many2many('hr.department', string='Departments')

    
    def print_reporte(self):
        run_id = self._context.get('active_id')
        pay_run = self.env['hr.payslip.run'].browse(run_id)
        companies = "Todas:"
        departamentos = "Todos"
        domain = [('payslip_run_id', '=', run_id)]
        if self.company_ids:
            domain.append(('company_id', 'in', self.company_ids.ids))
            companies = ','.join(['{}[{}]'.format(c.name, c.registro_patronal.name)
                                   for c in self.env['res.company'].sudo().browse(self.company_ids.ids)])
        else:
            companies += ','.join(['{}[{}]'.format(c.name, c.registro_patronal.name)
                                  for c in self.env['res.company'].sudo().search([])])
        if self.department_ids:
            domain.append(('employee_id.department_id', 'in', self.department_ids.ids))
            departamentos = ','.join([d.name for d in self.department_ids])

        payslips = self.env['hr.payslip'].search(domain, order='cod_emp ASC')
        if not payslips:
            raise ValidationError('No hay nominas con el criterio dado')

        data = {
            'payslip_ids': payslips.ids,
            'form': self.read(),
            'departamentos': departamentos,
            'companies': companies,
        }
        return self.env.ref('cfdi_nomina.action_reporte_prenominas').report_action(pay_run, data=data, config=False)

