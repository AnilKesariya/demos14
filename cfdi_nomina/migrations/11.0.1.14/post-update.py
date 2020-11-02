################################################
# Coded by: Jose Gpe Osuna joseg.osuna@gmail.com
################################################

from odoo import api, fields, models, _, SUPERUSER_ID
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info('Migracion Iniciada 14')
    from dateutil import relativedelta
    from datetime import datetime
    from ast import literal_eval

    env = api.Environment(cr, SUPERUSER_ID, {})

    acumulado_obj = env['hr.payslip.acumulado']
    payslip_obj = env['hr.payslip']
    empleados = env['hr.employee'].search([])
    # empleados = env['hr.employee'].search([('id', 'in', [4278, 4300])])
    total = len(empleados)
    i = 0
    for emp in empleados:
        i += 1
        _logger.info("({}/{}) {}".format(i, total, emp.nombre_completo))
        # Periodos mensuales, solo diciembre
        for mes in range(12, 13):
            ini_mes = datetime(year=2019, month=mes, day=1)
            fin_mes = ini_mes + relativedelta.relativedelta(months=+1, days=-1)
            nominas_mes = payslip_obj.search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'done'),
                ('date_from', '>=', ini_mes),
                ('date_to', '<=', fin_mes),
            ], order='date_from ASC')

            for slip in nominas_mes:
                _logger.info("{}  {}--{}".format(slip.name, slip.date_from, slip.date_to))
                sube_causado = slip._get_subsidio_causado()
                slip.subsidio_causado = round(sube_causado, 2)
                sube_causado_data = slip.get_acumulado_subsidio_causado_lines()
                _logger.info("sube_causado: {}, sube_causado_data: {}".format(sube_causado, sube_causado_data))

                subeacum_line = acumulado_obj.search([
                    ('slip_id', '=', slip.id),
                    ('name', '=', 'Subsidio causado')])
                subeacum_line.unlink()

                slip.write({
                    'acumulado_ids': [(0, 0, sube_causado_data)],
                })

    _logger.info('Migracion Terminada')


