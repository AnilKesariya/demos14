################################################
# Coded by: Jose Gpe Osuna joseg.osuna@gmail.com
################################################

from odoo import api, fields, models, _, SUPERUSER_ID
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    _logger.info('Migracion Iniciada 16')
    from dateutil import relativedelta
    from datetime import datetime
    from ast import literal_eval

    env = api.Environment(cr, SUPERUSER_ID, {})

    acumulado_obj = env['hr.payslip.acumulado']
    payslip_obj = env['hr.payslip']
    ICPSudo = env['ir.config_parameter'].sudo()

    fper = payslip_obj.get_fper()
    tabla_gravable_isr_id = env.ref('cfdi_nomina.hr_taxable_base_id1').id
    tabla_isr_id = literal_eval(ICPSudo.get_param('cfdi_nomina.NominaIPSTMensualID') or 'None')
    tabla_sube_id = literal_eval(ICPSudo.get_param('cfdi_nomina.NominaSUBEID') or 'None')

    empleados = env['hr.employee'].search([])
    # empleados = env['hr.employee'].search([('id', 'in', [4278, 4300])])
    total = len(empleados)
    i = 0
    for emp in empleados:
        i += 1
        _logger.info("({}/{}) {}".format(i, total, emp.nombre_completo))
        # Periodos mensuales, solo diciembre
        for mes in range(1, 2):
            ini_mes = datetime(year=2020, month=mes, day=1)
            fin_mes = ini_mes + relativedelta.relativedelta(months=+1, days=-1)
            nominas_mes = payslip_obj.search([
                ('employee_id', '=', emp.id),
                ('state', '=', 'done'),
                ('date_from', '>=', ini_mes),
                ('date_to', '<=', fin_mes),
            ], order='date_from ASC')

            for slip in nominas_mes:
                _logger.info("{}  {}--{}".format(slip.name, slip.date_from, slip.date_to))

                anual_lines = slip.get_anual_lines()
                data_grv = slip.get_acumulado_tabla(anual_lines, tabla_gravable_isr_id)
                total_grv_isr_nc = data_grv.get('actual_nc', 0)

                nominas_anuales = slip.get_anual_slip()

                total_grv_isr_mensuaL = 0
                if slip.tipo_calculo in ['mensual']:
                    total_grv_isr_mensuaL = total_grv_isr_nc * fper
                    _logger.info("total_grv_isr_nc: {} * {}".format(total_grv_isr_nc, fper))
                elif slip.tipo_calculo in ['ajustado', 'anual']:
                    total_grv_isr_mensuaL = total_grv_isr_nc
                    _logger.info("total_grv_isr_nc: {} ".format(total_grv_isr_nc))

                _logger.info("total_grv_isr_mensuaL calc: {}".format(total_grv_isr_mensuaL))

                ispt = env['hr.ispt'].get_valor(total_grv_isr_mensuaL, tabla_isr_id)

                slip.ispt = round(ispt, 2)
                ispt_calc = slip._get_ispt_calc()
                slip.ispt_calc = round(ispt_calc, 2)
                ispt_data = slip.get_acumulado_ispt_lines(nominas_anuales)
                _logger.info("ispt calc: {}, ispt_data: {}".format(ispt_calc, ispt_data))

                sube_calc = slip._get_sube_calc()
                slip.sube_calc = round(sube_calc, 2)
                sube_data = slip.get_acumulado_sube_lines(nominas_anuales)
                _logger.info("sube calc: {}, sube_data: {}".format(sube_calc, sube_data))

                acum_line = acumulado_obj.search([
                    ('slip_id', '=', slip.id),
                    ('name', 'in', ['ISPT', 'ISPT ', 'SUBE'])])
                acum_line.unlink()

                slip.write({
                    'acumulado_ids': [(0, 0, sube_data), (0, 0, ispt_data)],
                })

    _logger.info('Migracion Terminada')


