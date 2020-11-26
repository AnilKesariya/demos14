# -*- encoding: utf-8 -*-

import logging
import threading
from ast import literal_eval
from odoo import api, fields, models, _, registry
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)


class HrPayslipEmployees(models.TransientModel):
    _inherit = 'hr.payslip.employees'
    _description = 'hr payslip employees'

    def compute_sheet(self):
        # Full override a metodo original , cambios marcados con #JGO
        payslips = self.env['hr.payslip']
        [data] = self.read()
        active_id = self.env.context.get('active_id')
        if active_id:
            [run_data] = self.env['hr.payslip.run'].browse(active_id).read([
                'date_start', 'date_end', 'credit_note',
                'tipo_calculo', 'date_from', 'date_to',
                'fecha_pago', 'struct_id'])  # JGO

        from_date = run_data.get('date_start')
        to_date = run_data.get('date_end')
        tipo_calculo = run_data.get('tipo_calculo')  # JGO
        day_leave_from = run_data.get('date_from')  # JGO
        day_leave_to = run_data.get('date_to')   # JGO
        fecha_pago = run_data.get('fecha_pago')   # JGO
        struct_run_id = run_data.get('struct_id', [0])[0]    # JGO

        if not data['employee_ids']:
            raise UserError(
                _("You must select employee(s) to generate payslip(s)."))
        for employee in self.env['hr.employee'].browse(data['employee_ids']):
            e_from_date = self.env['hr.payslip'].check_start_date(
                employee, from_date)  # JGO
            e_day_leave_from = self.env['hr.payslip'].check_start_date(
                employee, day_leave_from)  # JGO

            # JGO, info del payroll en el context
            ctx = dict(
                self.env.context,
                default_day_leave_from=e_day_leave_from,
                default_day_leave_to=day_leave_to,
                struct_run_id=struct_run_id,
            )

            slip_data = self.env['hr.payslip'].with_context(ctx)._onchange_employee()
            # JGO, si se define Estructura en el procesamiento, se toma ese
            # valor
            struct_id = struct_run_id or slip_data['value'].get('struct_id')
            
            res = {
                'employee_id': employee.id,
                'name':"Abc",
                # 'name': slip_data['value'].get('name'),
                'struct_id': struct_id,  # JGO
                # 'contract_id': slip_data['value'].get('contract_id'),
                'payslip_run_id': active_id,
                # 'input_line_ids': [(0, 0, x) for x in slip_data['value'].get('input_line_ids')],
                # 'worked_days_line_ids': [(0, 0, x) for x in slip_data['value'].get('worked_days_line_ids')],
                'date_from': e_from_date,   # JGO
                'date_to': to_date,

                'day_leave_from': e_day_leave_from,   # JGO
                'day_leave_to': day_leave_to,    # JGO
                'tipo_calculo': tipo_calculo,   # JGO
                'fecha_pago': fecha_pago,   # JGO

                'credit_note': run_data.get('credit_note'),
                'company_id': employee.company_id.id,
                'registro_patronal_codigo': employee.company_id.registro_patronal.name,  # JGO
            }
            payslips += self.env['hr.payslip'].create(res)
        payslips.compute_sheet()
        return {'type': 'ir.actions.act_window_close'}


class HrPayslipRun(models.Model):
    _description = 'Payslip Batches'
    _name = 'hr.payslip.run'
    _inherit = ['hr.payslip.run', 'mail.thread', 'mail.activity.mixin']

    date_from = fields.Date(help='Used to get the lack to the employees',required=True)
    date_to = fields.Date(help='Used to get the lack to the employees',required=True)
    total = fields.Float('Total Amount', digits='Payroll', default=0.00)
    fecha_pago = fields.Date('Payment date',required=True)
    tipo_calculo = fields.Selection([
        ('anual', 'Anual'),
        ('ajustado', 'Ajustado'),
        ('mensual', 'Mensual'),
    ], 'Calculation type', default='mensual')
    # period_id = fields.Many2one(
    #    "account.period", string='Periodo', required=True)
    struct_id = fields.Many2one('hr.payroll.structure', string='Structure',required=True, 
                                readonly=True, states={'draft': [('readonly', False)]},
                                help='Defines the rules that have to be applied to this payslip, accordingly '
                                     'to the contract chosen. If you let empty the field contract, this field isn\'t '
                                     'mandatory anymore and thus the rules applied will be all the rules set on the '
                                     'structure of all contracts of the employee valid for the chosen period')
    journal_id = fields.Many2one('account.journal',string="Salary journal")
    

    @api.model
    def default_get(self, fields):
        res = super(HrPayslipRun, self).default_get(fields)

        if 'journal_id' in fields:
            config_journal_id = literal_eval(self.env['ir.config_parameter'].sudo(
            ).get_param('cfdi_nomina.NominaJournalID') or '0')
            if config_journal_id:
                res['journal_id'] = config_journal_id

        return res

    def unlink(self):
        for pr in self:
            if pr.slip_ids and len(pr.slip_ids):
                raise UserError(
                    _('Cannot be deleted as long as it has payroll included!'))
        return super(HrPayslipRun, self).unlink()

    def importar_faltas(self):

        modelo, tipo_ausencia_id = self.env['ir.model.data'].get_object_reference('hr_leave',
                                                                                  'holiday_status_unpaid')
        for nomina in self:
            for nomina_employee in nomina.slip_ids:
                if nomina_employee.state == 'done':
                    continue
                # datetime_start = fields.Datetime.context_timestamp(self, fields.Datetime.from_string(nomina.date_start))
                date_start = nomina.date_start
                date_to = nomina.date_end
                faltas_ids = self.env['hr.leave'].search([
                    ('employee_id', '=', nomina_employee.employee_id.id),
                    ('holiday_type', '=', 'employee'),
                    ('holiday_status_id', '=', tipo_ausencia_id),
                    ('date_from', '>=', date_start),
                    ('date_from', '<=', date_to),
                ])
                if faltas_ids:
                    for worked_line in nomina_employee.worked_days_line_ids:
                        if worked_line.code == 'WORK100':
                            number_of_days = worked_line.number_of_days
                            newworkdays = number_of_days - len(faltas_ids)
                            if newworkdays >= 0:
                                worked_line.number_of_days = newworkdays
                            break

            nomina.compute_sheet_run()
        return {}

    def _calculation_confirm_sheet_run(self):
        cntx = dict(self.env.context)
        cntx.update(payslip_run=self)
        with api.Environment.manage():
            with registry(self.env.cr.dbname).cursor() as new_cr:
                new_env = api.Environment(new_cr, self.env.uid, cntx)
                for sheet_run in self.with_env(new_env):
                    for payslip in sheet_run.slip_ids.filtered(lambda p: p.state == 'draft'):
                        payslip.with_env(new_env)._calculation_confirm_sheet(
                            use_new_cursor=self._cr.dbname)
        return {}

    def confirm_sheet_run(self):
        threaded_calculation = threading.Thread(
            target=self._calculation_confirm_sheet_run, name=self.id)
        threaded_calculation.start()
        return {}

    def compute_sheet_run_line(self):
        for sheet_run in self:
            amount_total = 0.0
            for payslip in sheet_run.slip_ids:
                amount_total += payslip.total
            sheet_run.write({'total': amount_total})
        return {}

    def compute_sheet_run(self):
        for sheet_run in self:
            amount_total = 0.0
            for payslip in sheet_run.slip_ids:
                amount_total += payslip.compute_sheet_total()
            sheet_run.total = amount_total
        return {}

    def send_mail(self):
        for sheet_run in self:
            if sheet_run.slip_ids:
                sheet_run.slip_ids.send_mail()
        return {}

    def action_calculate_sdi_last(self):
        for sheet_run in self:
            for slip in sheet_run.slip_ids:
                slip.calculate_sdi_last()
        return {}
