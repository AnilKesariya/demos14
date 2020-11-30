# -*- coding: utf-8 -*-
from datetime import datetime
from dateutil.relativedelta import relativedelta
from odoo.tools import float_compare
from odoo import api, models, fields, _
from odoo.exceptions import UserError
from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT


class Employee(models.Model):
    _inherit = 'hr.employee'
    # _rec_name = "nombre_completo"

    @api.depends('appat', 'apmat', 'name')
    def _nombre_completo(self):
        for rec in self:
            rec.nombre_completo = '%s %s %s' % (
                rec.name, rec.appat or '', rec.apmat or '')

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        res = super().name_search(
            name, args=args, operator=operator, limit=limit)
        args = args or []
        ids = self.search([('appat', 'ilike', name)] + args, limit=limit).ids
        ids2 = self.search([('apmat', 'ilike', name)] + args, limit=limit).ids
        try:
            ids3 = self.search(
                [('cod_emp', '=', name)] + args, limit=limit).ids
        except:
            ids3 = []
            pass
        ids += ids2
        ids += ids3

        search_domain = [('name', operator, name)]
        if ids:
            search_domain.append(('id', 'not in', ids))
        ids.extend(self.search(search_domain + args, limit=limit).ids)
        recs = self.browse(ids)
        if recs:
            res = recs.name_get()
        return res

    def name_get(self):
        result = []
        for rec in self:
            result.append((rec.id, "%s %s %s" % (
                rec.name, rec.appat or '', rec.apmat or '')))
        return result

    @api.depends('fecha_alta')
    def _get_anos_servicio(self):
        tz = self.env.user.tz or 'America/Mexico_City'
        ahora = fields.Datetime.context_timestamp(self.with_context(
            tz=tz), fields.Datetime.from_string(fields.Datetime.now()))
        # convertir ahora a naive datetime
        end_date = datetime.strptime(ahora.strftime(
            DEFAULT_SERVER_DATETIME_FORMAT), DEFAULT_SERVER_DATETIME_FORMAT)
        for employee in self:
            anos_servicio = 0
            if employee.fecha_alta:
                start_date = datetime.strptime(
                    str(employee.fecha_alta), DEFAULT_SERVER_DATE_FORMAT)
                anos_servicio = relativedelta(end_date, start_date).years
            employee.anos_servicio = anos_servicio

    def get_anos_servicio(self, fecha=None):
        self.ensure_one()
        # Años de servicio a una fecha dada
        if not fecha:
            end_date = datetime.strptime(
                fields.Datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)
        else:
            end_date = datetime.strptime(fecha, DEFAULT_SERVER_DATE_FORMAT)

        anos_servicio = 0
        if self.fecha_alta:
            start_date = datetime.strptime(
                self.fecha_alta, DEFAULT_SERVER_DATE_FORMAT)
            anos_servicio = relativedelta(end_date, start_date).years

        return anos_servicio

    def _get_age(self):
        self.ensure_one()
        if self.birthday:
            start_date = datetime.strptime(
                self.birthday, DEFAULT_SERVER_DATE_FORMAT)
            end_date = datetime.strptime(
                fields.Datetime.now(), DEFAULT_SERVER_DATETIME_FORMAT)
            return relativedelta(end_date, start_date).years

    # @api.depends('slip_ids.sdi') # Forzar a que se recalcule cada creacion de nomina
    # def _get_sdi(self):
    #
    #     for employee in self:
    #         # Ultima fecha de pago en la ultima nomina confirmada
    #         ultima_ids = self.env['hr.payslip'].search([
    #             ('employee_id', '=', employee.id),
    #             ('state', '=', 'done'),
    #         ], order='date_to DESC, number DESC', limit=1)
    #         if ultima_ids:
    #             employee.sueldo_imss = ultima_ids.sdi

    @api.model
    def default_get(self, fields):
        res = super(Employee, self).default_get(fields)
        if not res.get('dias_descanso_ids'):
            try:
                sunday_id = self.env.ref('cfdi_nomina.sunday').id
                res['dias_descanso_ids'] = [sunday_id]
            except ValueError:
                pass

        if not res.get('tabla_sdi_id'):
            try:
                tabla_sdi_id = self.env.ref('cfdi_nomina.hr_fi_id').id
                res['tabla_sdi_id'] = tabla_sdi_id
            except ValueError:
                pass

        if not res.get('tabla_vacaciones_id'):
            try:
                tabla_vac_id = self.env.ref('cfdi_nomina.hr_holiday_id').id
                res['tabla_vacaciones_id'] = tabla_vac_id
            except ValueError:
                pass

        return res

    sindicalizado = fields.Boolean(
        help='Check this box if the employee is unionized, otherwise leave off')
    tipo_jornada = fields.Many2one(
        "hr.ext.mx.tipojornada", string="Type of day")
    escolaridad = fields.Selection([
        ('primaria', 'Primaria'),
        ('secundaria', 'Secundaria'),
        ('prepa', 'Preparatoria'),
        ('licenciatura', 'Licenciatura')], string="Schooling")
    nombre_completo = fields.Char(compute=_nombre_completo, store=True)
    appat = fields.Char("Father's surname", size=64, required=True)
    apmat = fields.Char("Mother's surname", size=64, required=True)
    cod_emp = fields.Char(related="barcode", string="Employee Code", readonly=True,
                          help="Data taken from employee ID card")
    curp = fields.Char('CURP', size=18)
    imss = fields.Char('No. IMSS', size=64)
    registro_patronal = fields.Many2one(
        'hr.ext.mx.regpat', string='Employer Registration')
    fecha_alta = fields.Date('High date', required=True,
                             track_visibility='onchange')
    status_imss = fields.Selection([
        ('alta', 'Alta'),
        ('reingreso', 'Reingreso'),
        ('baja', 'Baja')], string="Status IMSS", default='alta', required=True)
    fecha_baja = fields.Date('Low date', track_visibility='onchange')
    causa_baja = fields.Selection([
        ('1', '1) Término contrato'),
        ('2', '2) Sep. Voluntaria'),
        ('3', '3) Abandono'),
        ('4', '4) Defunción'),
        ('5', '5) Clausura'),
        ('6', '6) Otras'),
        ('7', '7) Ausentismo'),
        ('8', '8) Rescisión de Contrato'),
        ('9', '9) Jubilación'),
        ('A', 'A) Pensión')
    ], string="Low Cause")
    rfc = fields.Char('RFC', size=13)
    infonavit = fields.Char('Infonavit', size=64)
    sar = fields.Char('SAR', size=64)
    tipo_sueldo = fields.Selection([
        ('fijo', 'Fija'), ('variable', 'Variable'), ('mixto', 'Mixta')],
        u"Contribution basis")
    zona_salario = fields.Many2one(
        'hr.ext.mx.zonasalario', string="Salary zone")
    sueldo_diario = fields.Float('Daily salary', track_visibility='onchange')
    tabla_sdi_id = fields.Many2one('hr.factor', 'SDI Table')
    tabla_vacaciones_id = fields.Many2one(
        'hr.vacation', 'Vacation Table')
    sueldo_imss = fields.Float(
        string='IMSS integrated salary', track_visibility='onchange')
    historico_sueldo_imss = fields.One2many(
        "hr.employee.historico.imss", "employee_id")
    sueldo_info = fields.Float('Infonavit integrated salary')
    sueldo_imss_bimestre_actual = fields.Float(
        'IMSS integrated salary (current bim)', track_visibility='onchange')
    retiro_parcialidad = fields.Float(
        'Retreat', help="Daily amount received by the worker for retirement, pension or retirement when the payment is partial")
    anos_servicio = fields.Integer(
        compute=_get_anos_servicio, string=u"Number of years of service")
    tarjeta_nomina = fields.Many2one(related="bank_account_id",string='Payroll card number', size=64)
    # tarjeta_nomina = fields.Char(string='Numero de tarjeta de nomina', size=64)
    ife_anverso = fields.Binary('Front', filters='*.png,*.jpg,*.jpeg')
    ife_reverso = fields.Binary('Back', filters='*.png,*.jpg,*.jpeg')
    ife_numero = fields.Char("Voter's key", size=64)
    licencia_anverso = fields.Binary('Front', filters='*.png,*.jpg,*.jpeg')
    licencia_reverso = fields.Binary('Back', filters='*.png,*.jpg,*.jpeg')
    licencia_numero = fields.Char('Number', size=64)
    licencia_vigencia = fields.Date('Validity')
    med_actividad = fields.Text("Activity within the company")
    med_antecedentes_1 = fields.Text("Family history")
    med_antecedentes_2 = fields.Text("Non-pathological personal history")
    med_antecedentes_3 = fields.Text("Personal Pathological History")
    med_padecimiento = fields.Text("Current condition")
    med_exploracion = fields.Text("Physical exploration")
    vehicle_distance = fields.Integer(
        string='Home-Work Dist.', help="In kilometers", groups="hr.group_hr_user")
    med_diagnostico = fields.Text("Diagnosis")
    med_apto = fields.Boolean("Suitable for the position")
    tipo_cuenta = fields.Selection([
        ('01', '01 Efectivo'),
        ('02', '02 Cheque nominativo'),
        ('03', '03 Transferencia electrónica de fondos'),
    ], 'Method of payment', default='02')
    no_fonacot = fields.Char('No. FONACOT', size=15)
    dias_descanso_ids = fields.Many2many(
        'hr.weekday', string='Days of rest')
    nombre_compelto = fields.Char(string="Full Name")

    transfers_count = fields.Integer(
        compute='_compute_transfers_count', string='Transfers')

    @api.model
    def create(self, vals):
        res = super(Employee, self).create(vals)
        if res and res.rfc and res.address_home_id and res.address_home_id.vat and \
                res.address_home_id.vat != res.rfc:
            raise UserError(_("The RFC does not match the Partner's RFC!"))
        return res

    def _compute_transfers_count(self):
        # read_group as sudo, since contract count is displayed on form view
        transfer_data = self.env['hr.employee.transfer'].sudo().read_group([('employee_id', 'in', self.ids)],
                                                                           ['employee_id'], ['employee_id'])
        result = dict((data['employee_id'][0], data['employee_id_count'])
                      for data in transfer_data)
        for employee in self:
            employee.transfers_count = result.get(employee.id, 0)

    # Se retira constraint ya que ahora cod_emp esta relacionado con el campo barcode
    # _sql_constraints = [
    #     ('cod_emp_uniq', 'unique (cod_emp)', 'Error! Ya hay un empleado con ese codigo.')
    # ]

    @api.onchange('fecha_baja')
    def onchange_fecha_baja(self):
        if self.fecha_baja:
            self.status_imss = 'baja'
        else:
            self.status_imss = 'alta'

    def write(self, vals):
        res = super(Employee, self).write(vals)
        for employee in self:
            if 'fecha_alta' in vals:
                    if employee.fecha_alta != vals['fecha_alta']:
                        employee.message_post(body=_(
                            'Se actualizo la fecha de alta de %s a %s') % (
                                employee.fecha_alta, vals['fecha_alta']
                        ))
            if 'fecha_baja' in vals:                
                    if employee.fecha_baja != vals['fecha_baja']:
                        employee.message_post(body=_(
                            'Se cambió la fecha de baja de %s a %s') % (
                            employee.fecha_baja, vals[
                                'fecha_baja']
                        ))

            if employee.rfc and employee.address_home_id and employee.address_home_id.vat and \
                    employee.address_home_id.vat != employee.rfc:
                    raise UserError(_("The RFC does not match the Partner's RFC!"))

            # if vals.get('fecha_baja'):
            #     vals.update(status_imss='baja')
            # else:
            #     vals.update(status_imss='alta')

            if vals.get('sueldo_imss'):
                # if self.sueldo_imss != vals.get('sueldo_imss'):
                if float_compare(self.sueldo_imss, vals.get('sueldo_imss', 0), precision_digits=2) != 0:
                    vals.update(historico_sueldo_imss=[(0, 0, {
                        'name': fields.Date.today(),
                        'sueldo_old': self.sueldo_imss,
                        'sueldo_new': vals.get('sueldo_imss'),
                        'user_id': self.env.uid
                    })])

        return res


class HistoricalSalaryIMSS(models.Model):
    _name = "hr.employee.historico.imss"
    _order = "name DESC"

    def _default_user_id(self):
        user_id = self.env.context.get('default_user_id', self.env.uid)
        return user_id

    name = fields.Date("Date", required=True,
                       default=fields.Date.context_today)
    sueldo_old = fields.Float("Previous salary")
    sueldo_new = fields.Float("New salary")
    employee_id = fields.Many2one("hr.employee", string="Employee")
    user_id = fields.Many2one(
        "res.users", string="Modified by", default=_default_user_id, readonly=True)


class HrApplicant(models.Model):
    _inherit = "hr.applicant"
    _description = 'Hr Applicant'

    def write(self, vals):
        first_name = vals.get("partner_first_name", "")
        appat = vals.get("appat", "")
        apmat = vals.get("apmat", "")
        if first_name and appat and apmat:
            vals["partner_name"] = first_name + " " + appat + " " + apmat
        return super().write(vals)

    @api.model
    def create(self, vals):
        res = super().create(vals)
        first_name = vals.get("partner_first_name", "")
        appat = vals.get("appat", "")
        apmat = vals.get("apmat", "")
        if first_name and appat and apmat:
            vals["partner_name"] = first_name + " " + appat + " " + apmat
        return res

    @api.onchange('partner_first_name', 'appat', 'apmat')
    def onchange_name(self):
        self.partner_name = '%s %s %s' % (
            self.partner_first_name, self.appat, self.apmat)

    partner_first_name = fields.Char("Name", )
    appat = fields.Char("Father's surname", )
    apmat = fields.Char("Mother's surname", )


    def create_employee_from_applicant(self):
        """ Create an hr.employee from the hr.applicants """
        employee = False
        for applicant in self:
            contact_name = False
            if applicant.partner_id:
                address_id = applicant.partner_id.address_get(['contact'])['contact']
                contact_name = applicant.partner_id.display_name
            else:
                if not applicant.partner_name:
                    raise UserError(_('You must define a Contact Name for this applicant.'))
                new_partner_id = self.env['res.partner'].create({
                    'is_company': False,
                    'type': 'private',
                    'name': applicant.partner_name,
                    'email': applicant.email_from,
                    'phone': applicant.partner_phone,
                    'mobile': applicant.partner_mobile
                })
                applicant.partner_id = new_partner_id
                address_id = new_partner_id.address_get(['contact'])['contact']
            if applicant.partner_name or contact_name:
                employee_data = {
                    'default_name': applicant.partner_name or contact_name,
                    'appat': applicant.appat,
                    'apmat': applicant.apmat,
                    'nombre_completo': '%s %s %s' % (
                        applicant.partner_first_name or applicant.name,
                        applicant.appat, applicant.apmat),
                    'fecha_alta': fields.Datetime.now(),
                    'default_job_id': applicant.job_id.id,
                    'default_job_title': applicant.job_id.name,
                    'address_home_id': address_id,
                    'default_department_id': applicant.department_id.id or False,
                    'default_address_id': applicant.company_id and applicant.company_id.partner_id
                    and applicant.company_id.partner_id.id or False,
                    'default_work_email': applicant.department_id and applicant.department_id.company_id
                    and applicant.department_id.company_id.email or False,
                    'default_work_phone': applicant.department_id.company_id.phone,
                    'form_view_initial_mode': 'edit',
                    'default_applicant_id': applicant.ids,
                    }
                    
                print("**employee_data***",employee_data)
                    
        dict_act_window = self.env['ir.actions.act_window']._for_xml_id('hr.open_view_employee_list')
        dict_act_window['context'] = employee_data
        return dict_act_window


