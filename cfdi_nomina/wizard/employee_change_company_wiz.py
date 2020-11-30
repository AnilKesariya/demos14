import logging
from odoo.exceptions import UserError
import datetime
from odoo import api, models, fields

_logger = logging.getLogger(__name__)


class HrEmployeeTransferWiz(models.TransientModel):
    _name = 'hr.employee.transfer.wiz'
    _rec_name = 'date'
    _description = 'Wizard para transferir company del empleado'

    date = fields.Date('Date', required=True, default=datetime.datetime.now())
    employee_id = fields.Many2one(
        'hr.employee', string='Employee', required=True)
    sueldo_diario = fields.Float(
        "Daily salary", related="employee_id.sueldo_diario", readonly=True)
    company_id = fields.Many2one(relation='res.company', related='employee_id.company_id',
                                 string='Warehouse', readonly=True)
    registro_patronal_id = fields.Many2one(relation='hr.ext.mx.regpat',
                                           related='company_id.registro_patronal',
                                           string='Employer Registration', readonly=True)
    company_dest_id = fields.Many2one(
        'res.company', string='Destination Warehouse', required=True)
    registro_patronal_dest_id = fields.Many2one(relation='hr.ext.mx.regpat',
                                                related='company_dest_id.registro_patronal',
                                                string='Employer Registration', readonly=True)

    department_id = fields.Many2one('hr.department', 'Department')
    job_id = fields.Many2one('hr.job', 'Job Title')
    contract_id = fields.Many2one('hr.contract', 'Contract', readonly=True)
    type_id = fields.Many2one(relation='hr.contract.type', related='contract_id.type_id',
                              string='Contract Type', readonly=True)
    date_start = fields.Date(
        'Start date', related='contract_id.date_start', readonly=True)
    wage = fields.Float('Daily salary contract')

    nomina_bim_anterior_ids = fields.Many2many(comodel_name="hr.payslip",
                                               relation="hr_employeetransferwiz_payslip_ant_rel",
                                               column1="hr_change_wiz_id",
                                               column2="payslip_id",
                                               string="Previous Bimester", readonly=True)
    nomina_bim_actual_ids = fields.Many2many(comodel_name="hr.payslip",
                                             relation="hr_employeetransferwiz_payslip_act_rel",
                                             column1="hr_change_wiz_id",
                                             column2="payslip_id",
                                             string="Current Quarter", readonly=True)

    bim_actual = fields.Char("Current Quarter", readonly=True)
    bim_anterior = fields.Char("Previous Bimester", readonly=True)

    state = fields.Selection([
        ('step1', 'Paso 1'),
        ('step2', 'Paso 2'),
    ], default='step1')

    # Registro patronal : employee.registro_patronal, company.registro_patronal

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if "employee_id" not in res:
            empleado = self.env["hr.employee"].browse(
                self._context.get("active_id"))
            res["employee_id"] = empleado.id
            res["department_id"] = empleado.department_id.id
            res["job_id"] = empleado.job_id.id

            contratos = self.env['hr.contract'].search([
                ('employee_id', '=', empleado.id),
                ('state', '=', 'open'),
            ], limit=1)   # Solo un contrato vigente (en proceso)

            if contratos:
                res["contract_id"] = contratos[0].id
                res["wage"] = contratos[0].wage

        return res

    def do_step1(self):
        self.state = 'step1'
        return {
            'type': 'ir.actions.act_window',
            'name': "Transferencia de Almacén",
            'res_model': self._name,
            'view_type': 'form',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': dict(self._context),
        }

    def do_step2(self):
        self.buscar_nominas()
        self.state = 'step2'
        return {
            'type': 'ir.actions.act_window',
            'name': "Transferencia de Almacén",
            'res_model': self._name,
            'view_type': 'form',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': dict(self._context),
        }

    def buscar_nominas(self):
        # Buscar los ultimos 2 meses completos de nomina confirmadas.
        # de acuerdo al calendario de la tabla IMSS
        tabla_id = self.env.ref('cfdi_nomina.hr_taxable_base_id2').id,
        tbgrv = self.env['hr.basegravable.acum'].browse(tabla_id)
        if not tbgrv:
            raise UserError('No hay tabla Base Gravable con id %s' % tabla_id)
        if not tbgrv.acum_calendar_id:
            raise UserError(
                'No hay calendario definido para la tabla Base Gravable %s' % tbgrv.name)

        # Datos del periodo actual
        str_start_date, str_end_date = tbgrv.acum_calendar_id.get_periodo_actual(
            self.date)

        self.bim_actual = "{} --- {}".format(str_start_date, str_end_date)

        nomina_bimestral_actual = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'done'),
            ('date_from', '>=', str_start_date),
            ('date_to', '<=', str_end_date),
            ('tipo_nomina', 'in', ['O', False]),  # Solo nominas ordinarias
            '|',
            ('registro_patronal_codigo', '=',
             self.company_id.registro_patronal.name),
            ('registro_patronal_codigo_new', '=',
             self.company_id.registro_patronal.name),
        ])
        nomina_bim_actual_ids = [(5, None, None)]
        for payslip in nomina_bimestral_actual:
            nomina_bim_actual_ids.append((4, payslip.id, None))

        # Datos del periodo anterior
        str_start_date, str_end_date = tbgrv.acum_calendar_id.get_periodo_anterior(
            self.date)

        self.bim_anterior = "{} --- {}".format(str_start_date, str_end_date)

        nomina_bimestral_anterior = self.env['hr.payslip'].search([
            ('employee_id', '=', self.employee_id.id),
            ('state', '=', 'done'),
            ('date_from', '>=', str_start_date),
            ('date_to', '<=', str_end_date),
            ('tipo_nomina', 'in', ['O', False]),  # Solo nominas ordinarias
            '|',
            ('registro_patronal_codigo', '=',
             self.company_id.registro_patronal.name),
            ('registro_patronal_codigo_new', '=',
             self.company_id.registro_patronal.name),
        ])
        nomina_bim_anterior_ids = [(5, None, None)]
        for payslip in nomina_bimestral_anterior:
            nomina_bim_anterior_ids.append((4, payslip.id, None))

        self.write({
            'nomina_bim_anterior_ids': nomina_bim_anterior_ids,
            'nomina_bim_actual_ids': nomina_bim_actual_ids,
        })

        return

    def cambiar(self):

        # Crea registro de la transferencia
        self.env['hr.employee.transfer'].create({
            'date': self.date,
            'employee_id': self.employee_id.id,
            # Registrar antes de cambiar la company del empleado related
            'company_id': self.company_id.id,
            'company_dest_id': self.company_dest_id.id,
            'wage': self.wage,
        })

        # Actualiza datos en el empleado
        address = self.company_dest_id.partner_id.address_get(['default'])
        self.employee_id.address_id = address['default'] if address else False
        self.employee_id.work_phone = self.employee_id.address_id.phone
        self.employee_id.mobile_phone = self.employee_id.address_id.mobile
        self.employee_id.company_id = self.company_dest_id
        self.employee_id.registro_patronal = self.registro_patronal_dest_id

        if self.employee_id.department_id != self.department_id:
            self.employee_id.department_id = self.department_id
            # Actualiza datos en el contrato vigente
            self.contract_id.department_id = self.department_id

        if self.employee_id.job_id != self.job_id:
            self.employee_id.job_id = self.job_id
            # Actualiza datos en el contrato vigente
            self.contract_id.job_id = self.job_id

        # Actualiza datos en el contrato vigente
        self.contract_id.company_id = self.company_dest_id
        if self.contract_id.wage != self.wage:
            self.contract_id.wage = self.wage
            self.employee_id.sueldo_diario = self.wage

        # Pone información del cambio en las nominas bimestrales anteriores a
        # la date dada
        registro_patronal_codigo_new = self.registro_patronal_dest_id.name
        for payslip in self.nomina_bim_actual_ids + self.nomina_bim_anterior_ids:
            payslip.registro_patronal_codigo_new = registro_patronal_codigo_new

        return False
