# -*- encoding: utf-8 -*-

from odoo import models, fields


class PaymentPeriodicity(models.Model):
    _name = "cfdi_nomina.periodicidad_pago"
    _description = "Payment Periodicity"

    name = fields.Char("Name", required=True)
    code = fields.Char(u"Catalog code SAT", required=True)


class ResourceResource(models.Model):
    _name = "cfdi_nomina.origen_recurso"
    _description = "Resource origin"

    name = fields.Char("Name", required=True)
    code = fields.Char(u"Catalog code SAT", required=True)


class Recruitment(models.Model):
    _name = "cfdi_nomina.regimen.contratacion"
    _description = "Recruitment regime"

    name = fields.Char(u"Description", required=True)
    code = fields.Char("Catalog code SAT", required=True)


class Risk(models.Model):
    _name = "cfdi_nomina.riesgo.puesto"
    _description = 'risk_class'

    name = fields.Char(u"Description", required=True)
    code = fields.Char("Catalog code SAT", required=True)


class TypeRule(models.Model):
    _name = "cfdi_nomina.tipo"
    _description = 'TypeRule'

    name = fields.Char("Type")


class GrouperCode(models.Model):
    _name = "cfdi_nomina.codigo.agrupador"
    _description = 'grouper_code'

    name = fields.Char("Name", required=True)
    code = fields.Char("Catalog code SAT", required=True)
    tipo_id = fields.Many2one("cfdi_nomina.tipo", string="Type", required=True)


class HoursType(models.Model):
    _name = "cfdi_nomina.tipo_horas"
    _description = "Hours type"

    name = fields.Char("Name", required=True)
    code = fields.Char(u"Catalog code SAT", required=True)


class DisabilityType(models.Model):
    _name = "cfdi_nomina.tipo_incapacidad"
    _description = "Disability type"

    name = fields.Char("Name", required=True)
    code = fields.Char(u"Catalog code SAT", required=True)


class DeductionType(models.Model):
    _name = "cfdi_nomina.tipo_deduccion"
    _description = "Type of deduction"

    name = fields.Char("Name", required=True)
    code = fields.Char(u"Catalog code SAT", required=True)


class DayType(models.Model):
    _name = "cfdi_nomina.tipo_jornada"
    _description = "Day type"

    name = fields.Char("Name", required=True)
    code = fields.Char(u"Catalog code SAT", required=True)


class OtherPaymentType(models.Model):
    _name = "cfdi_nomina.tipo_otro_pago"
    _description = "Type Other Payment"

    name = fields.Char("Name", required=True)
    code = fields.Char(u"Catalog code SAT", required=True)


class PerceptionType(models.Model):
    _name = "cfdi_nomina.tipo_percepcion"
    _description = "Perception Type"

    name = fields.Char("Name", required=True)
    code = fields.Char(u"Catalog code SAT", required=True)


class TypeWokingDay(models.Model):
    _name = "hr.ext.mx.tipojornada"
    _description = 'Day Type'

    name = fields.Char("Name", required=True)
    code = fields.Char(u"SAT Code")
