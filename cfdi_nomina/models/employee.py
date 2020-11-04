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
                tabla_sdi_id = self.env.ref('cfdi_nomina.tabla1_fi').id
                res['tabla_sdi_id'] = tabla_sdi_id
            except ValueError:
                pass

        if not res.get('tabla_vacaciones_id'):
            try:
                tabla_vac_id = self.env.ref('cfdi_nomina.tabla1_vac').id
                res['tabla_vacaciones_id'] = tabla_vac_id
            except ValueError:
                pass

        return res

    sindicalizado = fields.Boolean(
        help='Marque esta casilla si el empleado es sindicalizado, si no, deje desactivado')
    tipo_jornada = fields.Many2one(
        "hr.ext.mx.tipojornada", string="Tipo de jornada")
    escolaridad = fields.Selection([
        ('primaria', 'Primaria'),
        ('secundaria', 'Secundaria'),
        ('prepa', 'Preparatoria'),
        ('licenciatura', 'Licenciatura')], string="Escolaridad")
    nombre_completo = fields.Char(compute=_nombre_completo, store=True)
    appat = fields.Char('Apellido paterno', size=64, required=True)
    apmat = fields.Char('Apellido materno', size=64, required=True)
    cod_emp = fields.Char(related="barcode", string="Código de empleado", readonly=True,
                          help="Dato tomado del ID de credencial de empleado")
    curp = fields.Char('CURP', size=18)
    imss = fields.Char('No. IMSS', size=64)
    registro_patronal = fields.Many2one(
        'hr.ext.mx.regpat', string='Registro patronal')
    fecha_alta = fields.Date('Fecha alta', required=True,
                             track_visibility='onchange')
    status_imss = fields.Selection([
        ('alta', 'Alta'),
        ('reingreso', 'Reingreso'),
        ('baja', 'Baja')], string="Estatus IMSS", default='alta', required=True)
    fecha_baja = fields.Date('Fecha baja', track_visibility='onchange')
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
    ], string="Causa Baja")
    rfc = fields.Char('RFC', size=13)
    infonavit = fields.Char('Infonavit', size=64)
    sar = fields.Char('SAR', size=64)
    tipo_sueldo = fields.Selection([
        ('fijo', 'Fija'), ('variable', 'Variable'), ('mixto', 'Mixta')],
        u"Base cotización")
    zona_salario = fields.Many2one(
        'hr.ext.mx.zonasalario', string="Zona salario")
    sueldo_diario = fields.Float('Sueldo diario', track_visibility='onchange')
    tabla_sdi_id = fields.Many2one('hr.factor', 'Tabla SDI',)
    tabla_vacaciones_id = fields.Many2one(
        'hr.vacation', 'Tabla Vacaciones',)
    sueldo_imss = fields.Float(
        string='Sueldo integrado al IMSS', track_visibility='onchange')
    historico_sueldo_imss = fields.One2many(
        "hr.employee.historico.imss", "employee_id")
    sueldo_info = fields.Float('Sueldo integrado al Infonavit')
    sueldo_imss_bimestre_actual = fields.Float(
        'Sueldo integrado al IMSS (bim actual)', track_visibility='onchange')
    retiro_parcialidad = fields.Float(
        'Retiro', help="Monto diario percibido por el trabajador por jubilación, pensión o retiro cuando el pago es en parcialidades")
    anos_servicio = fields.Integer(
        compute=_get_anos_servicio, string=u"Número años de servicio")
    tarjeta_nomina = fields.Char('Numero de tarjeta de nomina', size=64)
    ife_anverso = fields.Binary('Anverso', filters='*.png,*.jpg,*.jpeg')
    ife_reverso = fields.Binary('Reverso', filters='*.png,*.jpg,*.jpeg')
    ife_numero = fields.Char('Clave de elector', size=64)
    licencia_anverso = fields.Binary('Anverso', filters='*.png,*.jpg,*.jpeg')
    licencia_reverso = fields.Binary('Reverso', filters='*.png,*.jpg,*.jpeg')
    licencia_numero = fields.Char('Numero', size=64)
    licencia_vigencia = fields.Date('Vigencia')
    med_actividad = fields.Text("Actividad dentro de la empresa")
    med_antecedentes_1 = fields.Text("Antecedentes heredo familiares")
    med_antecedentes_2 = fields.Text("Antecedentes personales no patologicos")
    med_antecedentes_3 = fields.Text("Antecedentes personales patologicos")
    med_padecimiento = fields.Text("Padecimento actual")
    med_exploracion = fields.Text("Exploracion fisica")
    vehicle_distance = fields.Integer(
        string='Home-Work Dist.', help="In kilometers", groups="hr.group_hr_user")
    med_diagnostico = fields.Text("Diagnostico")
    med_apto = fields.Boolean("Apto para el puesto")
    tipo_cuenta = fields.Selection([
        ('01', '01 Efectivo'),
        ('02', '02 Cheque nominativo'),
        ('03', '03 Transferencia electrónica de fondos'),
    ], 'Forma de pago', default='02')
    no_fonacot = fields.Char('No. FONACOT', size=15)
    dias_descanso_ids = fields.Many2many(
        'hr.weekday', string='Días de descanso')
    nombre_compelto = fields.Char(string="Nombre Compelto")

    transfers_count = fields.Integer(
        compute='_compute_transfers_count', string='Transferencias')

    def _compute_transfers_count(self):
        # read_group as sudo, since contract count is displayed on form view
        transfer_data = self.env['hr.employee.transfer'].sudo().read_group([('employee_id', 'in', self.ids)],
                                                                           ['employee_id'], ['employee_id'])
        result = dict((data['employee_id'][0], data['employee_id_count'])
                      for data in transfer_data)
        for employee in self:
            employee.transfers_count = result.get(employee.id, 0)

    def _check_rfc(self):
        for rec in self:
            if rec.address_home_id and rec.address_home_id.vat != rec.rfc:
                return False
        return True

    # Se retira constraint ya que ahora cod_emp esta relacionado con el campo barcode
    # _sql_constraints = [
    #     ('cod_emp_uniq', 'unique (cod_emp)', 'Error! Ya hay un empleado con ese codigo.')
    # ]

    _constraints = [
        (_check_rfc, 'El RFC no coincide con el del partner', ['rfc'])]

    @api.onchange('fecha_baja')
    def onchange_fecha_baja(self):
        if self.fecha_baja:
            self.status_imss = 'baja'
        else:
            self.status_imss = 'alta'

    def write(self, vals):
        if 'fecha_alta' in vals:
            for employee in self.filtered('fecha_alta'):
                if employee.fecha_alta != vals['fecha_alta']:
                    employee.message_post(body=_(
                        'Se actualizo la fecha de alta de %s a %s') % (
                            employee.fecha_alta, vals['fecha_alta']
                    ))

        if 'fecha_baja' in vals:
            for employee in self:
                if employee.fecha_baja != vals['fecha_baja']:
                    employee.message_post(body=_(
                        'Se cambió la fecha de baja de %s a %s') % (
                        employee.fecha_baja, vals[
                            'fecha_baja']
                    ))
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

        return super().write(vals)


class HistoricalSalaryIMSS(models.Model):
    _name = "hr.employee.historico.imss"
    _order = "name DESC"

    def _default_user_id(self):
        user_id = self.env.context.get('default_user_id', self.env.uid)
        return user_id

    name = fields.Date("Fecha", required=True,
                       default=fields.Date.context_today)
    sueldo_old = fields.Float("Sueldo anterior")
    sueldo_new = fields.Float("Sueldo nuevo")
    employee_id = fields.Many2one("hr.employee", string="Empleado")
    user_id = fields.Many2one(
        "res.users", string="Modificado por", default=_default_user_id, readonly=True)


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
        first_name = vals.get("partner_first_name", "")
        appat = vals.get("appat", "")
        apmat = vals.get("apmat", "")
        if first_name and appat and apmat:
            vals["partner_name"] = first_name + " " + appat + " " + apmat
        return super().create(vals)

    @api.onchange('partner_first_name', 'appat', 'apmat')
    def onchange_name(self):
        self.partner_name = '%s %s %s' % (
            self.partner_first_name, self.appat, self.apmat)

    partner_first_name = fields.Char("Nombre", )
    appat = fields.Char("Apellido paterno", )
    apmat = fields.Char("Apellido materno", )


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
