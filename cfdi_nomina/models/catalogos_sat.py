# -*- encoding: utf-8 -*-

from odoo import models, fields


class periodicidad_pago(models.Model):
    _name = "cfdi_nomina.periodicidad_pago"
    _description = "Periodicidad Pago"

    name = fields.Char("Nombre", required=True)
    code = fields.Char(u"Código catálogo SAT", required=True)


class origen_recurso(models.Model):
    _name = "cfdi_nomina.origen_recurso"
    _description = "Origen recurso"

    name = fields.Char("Nombre", required=True)
    code = fields.Char(u"Código catálogo SAT", required=True)


class regimen_contratacion(models.Model):
    _name = "cfdi_nomina.regimen.contratacion"
    _description = "Regimen contratacion"

    name = fields.Char(u"Descripción", required=True)
    code = fields.Char("Código catálogo SAT", required=True)


class clase_riesgo(models.Model):
    _name = "cfdi_nomina.riesgo.puesto"
    _description = 'clase_riesgo'

    name = fields.Char(u"Descripción", required=True)
    code = fields.Char("Código catálogo SAT", required=True)


class TipoRegla(models.Model):
    _name = "cfdi_nomina.tipo"
    _description = 'TipoRegla'
    name = fields.Char("Tipo")


class codigo_agrupador(models.Model):
    _name = "cfdi_nomina.codigo.agrupador"
    _description = 'codigo_agrupador'
    name = fields.Char("Nombre", required=True)
    code = fields.Char("Código catálogo SAT", required=True)
    tipo_id = fields.Many2one("cfdi_nomina.tipo", string="Tipo", required=True)


class tipo_horas(models.Model):
    _name = "cfdi_nomina.tipo_horas"
    _description = "Tipo horas"

    name = fields.Char("Nombre", required=True)
    code = fields.Char(u"Código catálogo SAT", required=True)


class tipo_incapacidad(models.Model):
    _name = "cfdi_nomina.tipo_incapacidad"
    _description = "Tipo incapacidad"

    name = fields.Char("Nombre", required=True)
    code = fields.Char(u"Código catálogo SAT", required=True)


class tipo_deduccion(models.Model):
    _name = "cfdi_nomina.tipo_deduccion"
    _description = "Tipo deduccion"

    name = fields.Char("Nombre", required=True)
    code = fields.Char(u"Código catálogo SAT", required=True)


class tipo_jornada(models.Model):
    _name = "cfdi_nomina.tipo_jornada"
    _description = "Tipo jornada"

    name = fields.Char("Nombre", required=True)
    code = fields.Char(u"Código catálogo SAT", required=True)


class tipo_otro_pago(models.Model):
    _name = "cfdi_nomina.tipo_otro_pago"
    _description = "Tipo Otro Pago"

    name = fields.Char("Nombre", required=True)
    code = fields.Char(u"Código catálogo SAT", required=True)


class tipo_percepcion(models.Model):
    _name = "cfdi_nomina.tipo_percepcion"
    _description = "Tipo Percepcion"

    name = fields.Char("Nombre", required=True)
    code = fields.Char(u"Código catálogo SAT", required=True)


class TipoJornada(models.Model):
    _name = "hr.ext.mx.tipojornada"
    _description = 'Tipo Jornada'

    name = fields.Char("Nombre", required=True)
    code = fields.Char(u"Código SAT")
