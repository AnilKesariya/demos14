# -*- coding: utf-8 -*-
################################################
# Coded by: Jose Gpe Osuna joseg.osuna@gmail.com
################################################
from datetime import datetime
from dateutil import relativedelta
from odoo.exceptions import ValidationError, UserError
from odoo import api, models, fields, _


class RegistroPatronal(models.Model):
    _name = 'hr.ext.mx.regpat'
    _description = 'Employer Registry'

    name = fields.Char("Numero", size=64, required=True)
    company_id = fields.Many2one("res.company", string="Company")
    UMA = fields.Float("UMA", help="UMA")
    SUB_IMSS = fields.Char("Subdelegación IMSS", help="SUB_IMSS")
    AG = fields.Selection([('A', 'A'), ('B', 'B'), ('C', 'C')],
                          "Área geográfica", default="A", help="AG", Rrequired=True)
    CP = fields.Char("Código Postal", help="AG")
    EXPED = fields.Char("Lugar de Expedición", help="EXPED",)

    # Cuotas del IMSS
    PRT_SF = fields.Float("Prima Riesgo de Trabajo Tope (PRT_SF)", digits=(
        8, 6), default=25.0, help="PRT_SF")
    PRT = fields.Float("Prima Riesgo de Trabajo (PRT)", digits=(
        8, 6), help="PRT")

    PE_SF = fields.Float("Prestaciones en Especie Tope (PE_SF)",
                         digits=(8, 4), default=25.0, help="PE_SF")
    PE_PATRON = fields.Float(
        "Prestaciones en Especie (PE_PATRON)", digits=(8, 4), help="PE_PATRON")

    AE3_SF = fields.Float("Prestaciones en Especie mayor 3 UMA Tompe (AE3_SF)", digits=(
        8, 4), default=25.0, help="AE3_SF")
    AE3_PATRON = fields.Float(
        "Prestaciones en Especie mayor 3 UMA (AE3_PATRON)", digits=(8, 4), help="AE3_PATRON")
    AE3_TRAB = fields.Float(
        "Prestaciones en Especie mayor 3 UMA (AE3_TRAB)", digits=(8, 4), help="AE3_TRAB")

    ED_SF = fields.Float("Prestaciones en dinero Tope (ED_SF)",
                         digits=(8, 4), default=25.0, help="ED_SF")
    ED_PATRON = fields.Float(
        "Prestaciones en dinero (ED_PATRON)", digits=(8, 4), help="ED_PATRON")
    ED_TRAB = fields.Float(
        "Prestaciones en dinero (ED_TRAB)", digits=(8, 4), help="ED_TRAB")

    IV_SF = fields.Float("Invalidéz y Vida Tope (IV_SF)",
                         digits=(8, 4), default=25.0, help="IV_SF")
    IV_PATRON = fields.Float(
        "Invalidéz y Vida (IV_PATRON)", digits=(8, 4), help="IV_PATRON")
    IV_TRAB = fields.Float("Invalidéz y Vida (IV_TRAB)",
                           digits=(8, 4), help="IV_TRAB")

    RET_SF = fields.Float("Retiro Tope (RET_SF)", digits=(
        8, 4), default=25.0, help="RET_SF")
    RET_PATRON = fields.Float("Retiro (RET_PATRON)",
                              digits=(8, 4), help="RET_PATRON")

    CEAV_SF = fields.Float("Cesantía Edad y Vejéz Tope (CEAV_SF)", digits=(
        8, 4), default=25.0, help="CEAV_SF")
    CEAV_PATRON = fields.Float(
        "Cesantía Edad y Vejéz (CEAV_PATRON)", digits=(8, 4), help="CEAV_PATRON")
    CEAV_TRAB = fields.Float(
        "Cesantía Edad y Vejéz (CEAV_TRAB)", digits=(8, 4), help="CEAV_TRAB")

    GUA_SF = fields.Float("Guarderías Tope (GUA_SF)",
                          digits=(8, 4), default=25.0, help="GUA_SF")
    GUA_PATRON = fields.Float(
        "Guarderías (GUA_PATRON)", digits=(8, 4), help="GUA_PATRON")

    GMP_SF = fields.Float("Gastos Médicos para Pens. Tope (GMP_SF)", digits=(
        8, 4), default=25.0, help="GMP_SF")
    GMP_PATRON = fields.Float(
        "Gastos Médicos para Pens. (GMP_PATRON)", digits=(8, 4), help="GMP_PATRON")
    GMP_TRAB = fields.Float(
        "Gastos Médicos para Pens. (GMP_TRAB)", digits=(8, 4), help="GMP_TRAB")

    INFONAVIT_SF = fields.Float("INFONAVIT Tope (INFONAVIT_SF)", digits=(
        8, 4), default=25.0, help="INFONAVIT_SF")
    INFONAVIT_PATRON = fields.Float(
        "INFONAVIT (INFONAVIT_PATRON)", digits=(8, 4), help="INFONAVIT_PATRON")


class ZonaSalario(models.Model):
    _name = 'hr.ext.mx.zonasalario'
    _description = 'Salary Zone'

    name = fields.Char("Nombre", size=64, required=True)
    sm = fields.Float("Salario Mínimo de la Zona")


class DiaSemana(models.Model):
    _name = 'hr.weekday'
    _description = 'Day week'

    name = fields.Char("Día", size=10, required=True)
    weekday = fields.Integer("Número", required=True)


class HrFactor(models.Model):
    _name = "hr.factor"
    _description = 'Integration Factor Table'

    name = fields.Char("Nombre")
    year_days = fields.Integer("Días del Año", default=365)
    fi_line_ids = fields.One2many(
        comodel_name="hr.factor.line", inverse_name="fi_id", string="Tabla", required=False,)

    @api.constrains('year_days')
    def _check_year_days(self):
        for rec in self:
            if not rec.year_days or rec.year_days <= 0:
                raise ValidationError(
                    _("Los días del año debe ser mayor que 0 y positivos."))
        return True

    def get_fi(self, years_old):
        """
        Busca el Factor de integracion para los años de antigüedad dados
        :param years_old: Años de antigüedad
        :return: el factor de integración. Si no lo encuentra regresa 1
        """
        fi = 1.0
        if self:
            self.ensure_one()
            # Busca el valor igual o inmediato superior a los años de servicio
            tabla_fi_ids = self.fi_line_ids.filtered(
                lambda line: line.years_old >= years_old)
            if tabla_fi_ids:
                fi = tabla_fi_ids[0].factor_integracion

        return fi

    def get_aguinaldo_days(self, years_old):
        """
        Busca el las vacaciones para los años de antigüedad dados
        :param years_old: Años de antigüedad
        :return: dias de aguinaldo o 0
        """
        aguinaldo_days = 0
        if self:
            self.ensure_one()
            # Busca el valor igual o inmediato superior a los años de servicio
            tabla_fi_ids = self.fi_line_ids.filtered(
                lambda line: line.years_old >= years_old)
            if tabla_fi_ids:
                aguinaldo_days = tabla_fi_ids[0].dias_aguinaldo

        return aguinaldo_days


class HrFactorLine(models.Model):
    _name = "hr.factor.line"
    _order = "years_old ASC"
    _description = 'Table Facor Integration Line'

    fi_id = fields.Many2one("hr.factor")
    years_old = fields.Integer(u"Años antigüedad",
                               help="Rango: valor mayor que la linea anterior y menor o igual al valor de esta linea")
    dias_aguinaldo = fields.Integer("Días aguinaldo")
    dias_vacaciones = fields.Integer("Días vacaciones")
    prima_vacacional = fields.Float("Prima vacacional")
    factor_integracion = fields.Float(
        u"Factor Integración", compute='_calcula_fi', digits=(5, 4), store=True)

    @api.depends('years_old', 'dias_aguinaldo', 'dias_vacaciones', 'prima_vacacional')
    def _calcula_fi(self):
        for record in self:
            b = record.dias_aguinaldo / record.fi_id.year_days  # 365.0
            c = record.dias_vacaciones * record.prima_vacacional / \
                record.fi_id.year_days  # 365.0
            record.factor_integracion = 1 + b + c


class HrVaction(models.Model):
    _name = "hr.vacation"
    _description = 'Vacation Table'

    name = fields.Char("Nombre")
    year_days = fields.Integer("Días del Año", default=365)
    vac_line_ids = fields.One2many(
        comodel_name="hr.vacation.line", inverse_name="vac_id", string="Tabla", required=False,)

    def get_vacation_days(self, years_old):
        """
        Busca el las vacaciones para los años de antigüedad dados
        :param years_old: Años de antigüedad
        :return: dias de vacaciones o 0
        """
        vacation_days = 0
        if self:
            self.ensure_one()
            # Busca el valor inmediato superior a los años de servicio
            tabla_vac_ids = self.vac_line_ids.filtered(
                lambda line: line.years_old > years_old)
            if tabla_vac_ids:
                vacation_days = tabla_vac_ids[0].dias_vacaciones

        return vacation_days

    def get_prima_vacation_days(self, years_old):
        """
        Busca los dias de prima vacaciononal para los años de antigüedad dados
        :param years_old: Años de antigüedad
        :return: prima vacacional o 0
        """
        prima_vacation_days = 0
        if self:
            self.ensure_one()
            # Busca el valor inmediato superior a los años de servicio
            tabla_vac_ids = self.vac_line_ids.filtered(
                lambda line: line.years_old > years_old)
            if tabla_vac_ids:
                prima_vacation_days = tabla_vac_ids[0].dias_prima_vacacional

        return prima_vacation_days


class HrVactionLine(models.Model):
    _name = "hr.vacation.line"
    _order = "years_old ASC"
    _description = 'Line Holidays Table'

    vac_id = fields.Many2one("hr.vacation")
    years_old = fields.Integer(u"Años antigüedad (lim inf)",
                               help="Rango: valor mayor que la linea anterior y menor o igual al valor de esta linea")
    dias_vacaciones = fields.Float("Días vacaciones")
    dias_prima_vacacional = fields.Float("Días Prima vacacional")


class HrCalendar(models.Model):
    _name = "hr.calendar.acum"
    _description = "To configure calendars and periods to accumulate"

    name = fields.Char("Nombre", required=True)
    fecha_inicio = fields.Date("Fecha Inicio", default=datetime(
        year=datetime.now().year, month=1, day=1), required=True)
    periodo = fields.Selection([
        ('1', 'Mensual'),
        ('2', 'Bimestral'),
        ('3', 'Trimestral'),
        ('6', 'Semestral'),
    ], 'Periodo', default='1')
    cal_line_ids = fields.One2many(comodel_name="hr.calendar.acum.line", inverse_name="cal_id", string="Tabla",
                                   required=False, )

    def fill(self):

        if not self.periodo:
            return

        period = int(self.periodo)
        date1 = Datetime.from_string(self.fecha_inicio)
        lines = [(5, 0)]
        sequence = 1
        for i in range(0, 12, period):
            date2 = date1 + \
                relativedelta.relativedelta(months=+period, days=-1)
            lines.append([0, 0, {
                'sequence': sequence,
                'fecha_inicio': date1,
                'fecha_fin': date2,
            }])
            date1 = date2 + relativedelta.relativedelta(days=+1)
            sequence += 1

        self.cal_line_ids.unlink()
        self.cal_line_ids = lines

    def get_periodo_anterior(self, fecha):
        self.ensure_one()
        periodo = self.cal_line_ids.filtered(lambda r: r.fecha_fin < fecha)
        if not periodo:
            # raise UserError('No se encontró periodo anterior a la fecha %s en calendario %s' % (fecha, self.name))
            return False, False

        # El ultimo elemento de la lista filtrada
        return periodo[-1].fecha_inicio, periodo[-1].fecha_fin

    def get_periodo_actual(self, fecha):
        self.ensure_one()
        periodo = self.cal_line_ids.filtered(
            lambda r: r.fecha_inicio <= fecha <= r.fecha_fin)
        if not periodo:
            raise UserError(
                'No se encontró periodo actual a la fecha %s en el calendario %s' % (fecha, self.name))

        # El primer elemento de la lista filtrada
        return periodo[0].fecha_inicio, periodo[0].fecha_fin

    def get_periodo_siguiente(self, fecha):
        self.ensure_one()
        periodo = self.cal_line_ids.filtered(lambda r: r.fecha_inicio > fecha)
        if not periodo:
            raise UserError(
                'No se encontró periodo siguiente a la fecha %s en el calendario %s' % (fecha, self.name))

        # El primer elemento de la lista filtrada
        return periodo[0].fecha_inicio, periodo[0].fecha_fin


class HrCalendarLine(models.Model):
    _name = "hr.calendar.acum.line"
    _order = "cal_id, sequence"
    _description = 'Calendar Acum Line Table'

    cal_id = fields.Many2one("hr.calendar.acum")
    sequence = fields.Integer("Secuencia", required=True)
    fecha_inicio = fields.Date("Fecha Inicio", required=True)
    fecha_fin = fields.Date("Fecha Fin", required=True)

    @api.model
    def default_get(self, fields):
        res = super(TablaCalendarAcumLine, self).default_get(fields)
        lines = self.env['hr.calendar.acum'].new(
            'cal_line_ids', self._context.get('cal_line_ids'), ['fecha_fin'])

        period = int(self._context.get('periodo', '1'))

        if not lines and 'fecha_inicio' in res:
            res['fecha_fin'] = Datetime.from_string(res['fecha_inicio']) + relativedelta.relativedelta(
                months=+period, days=-1)
            res['sequence'] = 1

        if lines and lines[-1] and 'fecha_fin' not in res:
            fecha2_dt = Datetime.from_string(lines[-1].get('fecha_fin'))
            res['fecha_inicio'] = fecha2_dt + \
                relativedelta.relativedelta(days=+1)
            res['fecha_fin'] = fecha2_dt + \
                relativedelta.relativedelta(months=+period)
            res['sequence'] = len(lines) + 1

        return res


class HrTaxableBase(models.Model):
    _name = "hr.basegravable.acum"
    _order = "sequence"
    _description = 'Acum Taxable Base Table'

    sequence = fields.Integer("Secuencia", readonly=1)
    name = fields.Char("Nombre", readonly=1)
    data_field = fields.Char("Campo", help='Campo cuyo valor se va a acumular')
    acum_calendar_id = fields.Many2one('hr.calendar.acum', string='Calendario',
                                       help='Calendario para acumulados en nomina')


class HrSubsidy(models.Model):
    _name = "hr.employment.sube"
    _description = 'Employment Subsidy Table'

    name = fields.Char('Nombre', required=True, default=datetime.now().year)
    tabla_line = fields.One2many(
        'hr.employment.sube.line', 'tabla_id', string='Lineas')

    @api.model
    def get_valor(self, ingreso, tabla_id):
        """
        Busca el subisido para el ingreso dado
        :param ingreso: Ingreso
        :return: subsidio
        """
        if not tabla_id:
            raise ValidationError(
                'No se ha establecido las tablas para Subsidio en los ajustes de nómina')
        sube = 0
        # Busca el valor igual o inmediato superior al limite inferior y el año
        tabla_sube = self.env['hr.employment.sube.line'].search([
            ('tabla_id', '=', tabla_id),
            ('limite_inferior', '<=', ingreso),
            ('limite_superior', '>=', ingreso),
        ], limit=1)
        if tabla_sube:
            sube = tabla_sube.subsidio

        return sube


class HrSubsidyLine(models.Model):
    _name = "hr.employment.sube.line"
    _order = "limite_inferior"
    _description = 'Table Subsidy Employment Line'

    tabla_id = fields.Many2one('hr.employment.sube')
    limite_inferior = fields.Float("Limite inferior")
    limite_superior = fields.Float("Limite superior")
    subsidio = fields.Float("Subsidio")


    # @api.model
    # def default_get(self, default_fields):
    #     res = super(HrSubsidyLine, self).default_get(default_fields)
    #     if self._context.get('tabla_line'):
    #         lines = self.env['hr.employment.sube'].new(
    #             {'tabla_line': self._context['tabla_line']})
    #     print('lines', lines)
    #     if lines and lines[-1] and 'limite_inferior' not in res:
    #         limsup2 = lines[-1]
    #         res['limite_inferior'] = limsup2 + 0.01
    #         res['limite_superior'] = limsup2 + 1
    #     return res


    # @api.model
    # def default_get(self, fields):
    #     res = super(HrSubsidyLine, self).default_get(fields)
    # lines = self.env['hr.employment.sube'].new(
    #     'tabla_line', self._context.get('tabla_line'), ['limite_superior'])
    # print('self._context.gettabla_line', self._context.get('tabla_line'))
    # print(self._context.get('tabla_line'), ['limite_inferior'])
    # lines = self.env['hr.employment.sube'].new(
    #     {'tabla_line', self._context.get('tabla_line'), ['limite_inferior']})
    # if lines and lines[-1] and 'limite_inferior' not in res:
    #     limsup2 = lines[-1].get('limite_superior')
    #     res['limite_inferior'] = limsup2 + 0.01
    #     res['limite_superior'] = limsup2 + 1

    # return res


class HrIspt(models.Model):
    _name = "hr.ispt"
    _description = 'Tabla ISPT'

    name = fields.Char('Nombre', required=True, default=datetime.now().year)
    tabla_line = fields.One2many(
        'hr.ispt.line', 'tabla_id', string='Lineas')

    @api.model
    def get_valor(self, ingreso, tabla_id):
        """
        Busca el subisido para el ingreso dado
        :param ingreso: Ingreso
        :return: subsidio
        """
        if not tabla_id:
            raise ValidationError(
                'No se ha establecido las tablas para ISR en los ajustes de nómina')

        ispt = 0
        # Busca el valor igual o inmediato superior al limite inferior y el año
        tabla_ispt = self.env['hr.ispt.line'].search([
            ('tabla_id', '=', tabla_id),
            ('limite_inferior', '<=', ingreso),
            ('limite_superior', '>=', ingreso), ], limit=1)
        if tabla_ispt:

            ispt = (ingreso - tabla_ispt.limite_inferior) * \
                tabla_ispt.porc_excedente / 100.0 + tabla_ispt.cuota_fija

        return ispt


class HrIsptLine(models.Model):
    _name = "hr.ispt.line"
    _order = "limite_inferior"
    _description = 'Tabla ISPT Line'

    tabla_id = fields.Many2one('hr.ispt')
    limite_inferior = fields.Float("Limite inferior")
    limite_superior = fields.Float("Limite superior")
    cuota_fija = fields.Float("Cuota fija")
    porc_excedente = fields.Float("% sobre excedente de limite inferior")

    # @api.model
    # def default_get(self, fields):
    #     res = super(HrIsptLine, self).default_get(fields)
    #     lines = self.env['hr.ispt'].new(
    #         'tabla_line', self._context.get('tabla_line'), ['limite_superior'])

    #     if lines and lines[-1] and 'limite_inferior' not in res:
    #         limsup2 = lines[-1].get('limite_superior')
    #         res['limite_inferior'] = limsup2 + 0.01
    #         res['limite_superior'] = limsup2 + 1

    #     return res
