################################################
# Coded by: Jose Gpe Osuna joseg.osuna@gmail.com
################################################

from odoo import api, fields, models, _, SUPERUSER_ID
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info('Migracion Iniciada')
    from dateutil import relativedelta
    from datetime import datetime
    from ast import literal_eval

    env = api.Environment(cr, SUPERUSER_ID, {})

    ICPSudo = env['ir.config_parameter'].sudo()
    tabla_sube_id = literal_eval(ICPSudo.get_param('cfdi_nomina.NominaSUBEID') or None)
    tabla_sube = env['hr.employment.sube']
    acumulado_obj = env['hr.payslip.acumulado']
    payslip_obj = env['hr.payslip']
    fper = 365.0 / 12.0 / 15.0
    empleados = env['hr.employee'].search([])
    # empleados = env['hr.employee'].search([('id', 'in', [4278, 4300])])
    total = len(empleados)
    i = 0
    for emp in empleados:
        i += 1
        _logger.info("({}/{}) {}".format(i, total, emp.nombre_completo))
        # Periodos mensuales
        sube_causado_acum_anual = sube_causado_acum_nc = 0
        for mes in range(1, 13):
            ini_mes = datetime(year=2019, month=mes, day=1)
            fin_mes = ini_mes + relativedelta.relativedelta(months=+1, days=-1)
            nominas_mes = payslip_obj.search([
                ('employee_id', '=', emp.id),
                ('tipo_calculo', 'in', ['mensual', 'ajustado']),
                ('state', '=', 'done'),
                ('date_from', '>=', ini_mes),
                ('date_to', '<=', fin_mes),
            ], order='date_from ASC')

            sube_causado_acum_anterior = sube_causado_acum_nc
            sube_causado_acum_ac = 0
            for slip in nominas_mes:

                if mes == 1:
                    _logger.info("Acumulados de enero ...")
                    # recalcula acumulados en enero por error historico
                    slip.recalc_acumulados()
                    # base_gravable1 = slip.acumulado_ids.filtered(lambda l: l.name == "Base Gravable ISR")
                    base_gravable_line = acumulado_obj.search([
                        ('slip_id', '=', slip.id),
                        ('name', '=', 'Base Gravable ISR')])

                    base_gravable_actual_nc = base_gravable_line.actual_nc
                    if slip.tipo_calculo == 'mensual':
                        base_gravable = base_gravable_actual_nc * fper
                    else:  # ajustado
                        base_gravable = base_gravable_actual_nc

                    sube = tabla_sube.get_valor(base_gravable, tabla_sube_id)

                    slip.sube = sube

                sube = slip.sube or 0

                if slip.tipo_calculo == 'mensual':
                    sube_causado = round(sube / fper, 2)
                else:  # ajustado
                    sube_causado = round(sube - sube_causado_acum_ac, 2)

                _logger.info("slip date: {}, Sube calc: {}, Sube alm: {}, Causado: {}".format(
                    slip.date_to, sube, slip.sube, sube_causado))

                sube_causado_acum_nc = sube_causado_acum_ac + sube_causado
                sube_causado_data = {
                    'name': 'Subsidio causado',
                    'actual_nc': sube_causado_acum_nc,
                    'actual_ac': sube_causado_acum_ac,
                    'anterior': sube_causado_acum_anterior,
                    'anual': sube_causado_acum_anual,
                }

                sube_causado_acum_ac += sube_causado
                sube_causado_acum_anual += sube_causado

                subeacum_line = acumulado_obj.search([
                    ('slip_id', '=', slip.id),
                    ('name', '=', 'Subsidio causado')])
                subeacum_line.unlink()

                slip.write({
                    'acumulado_ids': [(0, 0, sube_causado_data)],
                    'subsidio_causado': sube_causado,
                })

    _logger.info('Migracion Terminada')


