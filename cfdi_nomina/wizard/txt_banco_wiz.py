import logging
import base64
from odoo.exceptions import ValidationError, UserError
from odoo import api, models, fields

_logger = logging.getLogger(__name__)


class TxtBancoWiz(models.TransientModel):
    _name = 'txt.banco.wiz'
    _description = 'Wizard for Generating Bank Dispersion Text'

    company_ids = fields.Many2many('res.company', string='Compañías')

    id_concepto = fields.Selection([
        ('01 Pago de Nomina', '01 Pago de Nomina'),
        ('02 Pago de Vacaciones', '02 Pago de Vacaciones'),
        ('03 Pago de Gratificaciones', '03 Pago de Gratificaciones'),
        ('04 Pago de Comisiones', '04 Pago de Comisiones'),
        ('05 Pago de Beca', '05 Pago de Beca'),
        ('06 Pago de Pension', '06 Pago de Pension'),
        ('07 Pago de Subsidios', '07 Pago de Subsidios'),
        ('08 Otros pagos por Transferencia', '08 Otros pagos por Transferencia'),
        ('09 Pago de Honorarios', '09 Pago de Honorarios'),
        ('10 Pago de Prestamo', '10 Pago de Prestamo'),
        ('11 Pago de Viaticos', '11 Pago de Viaticos'),
    ], string='ID Concepto', required=True, default='01 Pago de Nomina')

    opt_tipo_pago = fields.Selection([('todos', 'Todos'), ('transfer', 'Transferencias')], 'Tipo de pago',
                                     default='todos')

    data_file = fields.Binary('File generated', filters='*.csv,*.txt', readonly=True)
    data_fname = fields.Char('File Name')

    uma = fields.Float('UMA')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._context.get("cuotas_obrero_patronal"):
            # Temporal.. luego lo quitaremos
            uma = 0
            run_ids = self._context.get('active_ids')
            pay_runs = self.env['hr.payslip.run'].browse(run_ids)
            for run in pay_runs:
                for payslip in run.slip_ids:
                    uma = payslip.employee_id.company_id.registro_patronal.UMA
                    break
            res.update(data_fname='X', uma=uma)

        return res

    
    def gen_txt(self):
        run_ids = self._context.get('active_ids')
        domain = [('payslip_run_id', 'in', run_ids)]

        if self.opt_tipo_pago == 'transfer':
            domain += [('employee_id.tipo_cuenta', '=', '03')]

        if self.company_ids:
            domain.append(('company_id', 'in', self.company_ids.ids))

        archivo = ''
        # for p in pay_run.slip_ids:
        for p in self.env['hr.payslip'].search(domain):
            line = '{appat},{apmat},{nombre},{cuenta},{importe},{id_concepto},{company}\n'.format(
                appat=p.employee_id.appat,
                apmat=p.employee_id.apmat,
                nombre=p.employee_id.name,
                cuenta=p.employee_id.bank_account_id and p.employee_id.bank_account_id.acc_number or '',
                importe=p.total,
                id_concepto=self.id_concepto,
                company=p.company_id.name,
            )
            archivo += line

        if not archivo:
            raise ValidationError('No hay nominas con el criterio dado')

        self.data_file = base64.encodebytes(archivo.encode('utf-8'))
        self.data_fname = 'Dispersion.csv'

        return {
            'type': 'ir.actions.act_window',
            'name': 'Texto Dispersion Banco Generado',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': self.id,
            'target': 'new',
        }

    def action_update(self):
        # Temporal.. luego lo quitaremos
        run_ids = self._context.get('active_ids')
        pay_runs = self.env['hr.payslip.run'].browse(run_ids)
        for run in pay_runs:
            for payslip in run.slip_ids:
                payslip.calc_cuotas_obrero_patronal(uma=self.uma)

        return {}
