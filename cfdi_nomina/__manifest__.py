# -*- coding: utf-8 -*-
##############################################################################
#
#    AtharvERP Business Solutions
#    Copyright (C) 2020-TODAY AtharvERP Business Solutions(<http://www.atharverp.com>).
#    Author: AtharvERP Business Solutions(<http://www.atharverp.com>)
#    you can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    It is forbidden to publish, distribute, sublicense, or sell copies
#    of the Software or modified copies of the Software.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    GENERAL PUBLIC LICENSE (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'CFDI Nomina Mexico - Payroll',
    'version': '14.0.0.1.0',
    'author': "AtharvERP Business Solutions",
    'maintainer': 'AtharvERP Business Solutions',
    'website': "http://www.atharverp.com",
    'category': 'Localization',
    'depends': [
        'l10n_mx_edi',
        'hr_payroll_account',
        'hr_recruitment',
        'hr_work_entry_contract',
        'hr_attendance',
        'hr_oisa',
        'hr_holidays',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/cfdi_nomina.tipo.csv',
        'data/cfdi_nomina.regimen.contratacion.csv',
        'data/cfdi_nomina.riesgo.puesto.csv',
        'data/cfdi_nomina.origen_recurso.csv',
        'data/cfdi_nomina.periodicidad_pago.csv',
        'data/cfdi_nomina.tipo_horas.csv',
        'data/hr.contract.type.csv',
        'data/cfdi_nomina.codigo.agrupador.csv',
        'data/ir_cron.xml',
        'data/catalog.xml',
        # 'data/res_bank.xml',
        'data/mail_template_data.xml',
        'views/account_journal_view.xml',
        'views/agrupacion_view.xml',
        'views/hr_tablas_view.xml',
        'views/hr_transfer_view.xml',
        'views/res_bank_view.xml',
        'views/hr_view.xml',
        'views/hr_pendientes_timbrar_view.xml',
        'views/tipo_view.xml',
        'views/res_company_view.xml',
        'views/hr_payslip_line_view.xml',
        'views/employee_view.xml',
        'views/menus.xml',
        'views/partner_view.xml',
        'views/hr_movimiento_nomina_view.xml',
        'views/contract_report.xml',
        'views/attendance_report.xml',
        'wizard/reporte_acumulado_2_view.xml',
        'wizard/batch_mail_view.xml',
        'wizard/hr_attendance_wiz_view.xml',
        'wizard/txt_banco_wiz_view.xml',
        'views/recibo_nomina_report.xml',
        'wizard/batch_cfdi_view.xml',
        'views/hr_payroll_view.xml',
        'views/hr_holiday_status.xml',
        'views/res_config_settings_views.xml',
        'views/prenominas_report.xml',
        'views/liqimss_report.xml',
        'wizard/reporte_prenominas_wiz_view.xml',
        'wizard/reporte_liqimss_wiz_view.xml',
        'wizard/genera_laypoliza_wiz_view.xml',
        'wizard/idse_wiz_view.xml',
        'wizard/employee_change_company_wiz_view.xml',
        'security/security.xml'
    ],
    'demo': [
        # "demo/salary_rule_demo.xml",
        # "demo/payroll_structure_demo.xml",
    ],
    'installable': True,
}
