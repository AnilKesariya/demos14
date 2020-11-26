import logging
from odoo.exceptions import ValidationError, UserError
import xlwt
from io import StringIO
from tempfile import NamedTemporaryFile
import base64

from odoo import api, models, fields

_logger = logging.getLogger(__name__)


class HrGenLayPolizaWiz(models.TransientModel):
    _name = 'hr.genera.laypoliza.wiz'
    _description = 'Wizard for Generating Payroll Policies'

    company_ids = fields.Many2many('res.company', string='Companies')
    data_file = fields.Binary('File generated', filters='*.csv,*.txt', readonly=True)
    data_fname = fields.Char('File Name')
    avisos = fields.Text('Notices', readonly=1, default='')

    
    def gen_laypoliza(self):
        run_ids = self._context.get('active_ids')
        domain = [('payslip_run_id', 'in', run_ids)]
        if self.company_ids:
            domain.append(('company_id', 'in', self.company_ids.ids))

        payslips = self.env['hr.payslip'].search(domain, order='cod_emp ASC')
        if not payslips:
            raise ValidationError('No hay nominas con el criterio dado')

        data = self.get_poliza_data(payslips)

        wbk = xlwt.Workbook(encoding='utf-8')
        # fl = StringIO()
        # Estilos
        _bc = '22'  # borders color
        decimal_format = '#,##0.00'
        style_linea = xlwt.easyxf('font:height 210;font:name Calibri; align: wrap true, vert top, horiz left;'
                                  'borders: '
                                  'left thin, right thin, top thin, bottom thin, '
                                  'left_colour %s, right_colour %s, '
                                  'top_colour %s, bottom_colour %s;'
                                  % (_bc, _bc, _bc, _bc),
                                  )
        style_bold = xlwt.easyxf('font:height 210;font:name Calibri; font:bold true; align: wrap true, vert top;;'
                                 'borders: '
                                 'left thin, right thin, top thin, bottom thin, '
                                 'left_colour %s, right_colour %s, '
                                 'top_colour %s, bottom_colour %s;'
                                 % (_bc, _bc, _bc, _bc),
                                 )
        style_decimal = xlwt.easyxf(num_format_str=decimal_format)
        style_total = xlwt.easyxf('font:height 210;font:name Calibri; font:bold true; align: wrap true, vert top;;'
                                    'borders: '
                                    'left thin, right thin, top thin, bottom thin, '
                                    'left_colour %s, right_colour %s, '
                                    'top_colour %s, bottom_colour %s;'
                                    % (_bc, _bc, _bc, _bc), num_format_str=decimal_format
                                    )

        # Hojas de trabajo
        for dhoja in data:
            sheet = wbk.add_sheet(dhoja.get('name'), cell_overwrite_ok=True)
            for col, h in enumerate(dhoja.get('header')):
                sheet.write(0, col, h.get('titulo'), style_bold)
                sheet.col(col).width = h.get('ancho') * 12

            lin = 0
            for lin, ld in enumerate(dhoja.get('lineas')):
                for col, d in enumerate(ld):
                    sheet.write(lin + 1, col, d)

            # Totales
            lastrow = lin + 3
            sheet.write(lastrow, 7, xlwt.Formula('SUM(H1:H{})'.format(lastrow - 1)), style_total)
            sheet.write(lastrow, 8, xlwt.Formula('SUM(I1:I{})'.format(lastrow - 1)), style_total)
            # sheet.col(8).style = style_decimal
            # sheet.col(9).style = style_decimal

        real_filename = NamedTemporaryFile()
        # wbk.save(real_filename.name)
        file1 = open(real_filename.name, 'rb')

        self.data_file = base64.encodebytes(file1.read())
        self.data_fname = "CargaNomina{}.xls".format('N')

        return {
            'type': 'ir.actions.act_window',
            'name': 'Layout Nomina Generado',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': self.id,
            'target': 'new',
        }

    def get_poliza_data(self, payslips):

        head = [
            {
                'titulo': 'CIA',
                'ancho': 200,
            },
            {
                'titulo': 'CUENTA',
                'ancho': 400,
            },
            {
                'titulo': 'DEPARTAMENTO',
                'ancho': 500,
            },
            {
                'titulo': 'ALMACEN',  # En employee.company_id.x_id_almacen
                'ancho': 400,
            },
            {
                'titulo': 'REGION',   # En employee.company_id.xs_id_region
                'ancho': 200,
            },
            {
                'titulo': 'LINEA',
                'ancho': 200,
            },
            {
                'titulo': 'ASOCIADO',
                'ancho': 400,
            },
            {
                'titulo': 'Suma de Cargo',
                'ancho': 400,
            },
            {
                'titulo': 'Suma de Abono',
                'ancho': 400,
            },
        ]
        p_id = self.env.ref("cfdi_nomina.catalogo_tipo_percepcion").id
        d_id = self.env.ref("cfdi_nomina.catalogo_tipo_deduccion").id
        o_id = self.env.ref("cfdi_nomina.catalogo_tipo_otro_pago").id

        # Ofix
        idregion_dict = dict(self.env['res.company']._fields['xs_id_region']._description_selection(self.env))

        data_dict = {}
        data_dict_sub = {}   # Para subototales por tipo de pago
        resumen_poliza_dict = {} # Para agrupar lienas si regla salarial x_nivel_poliza indica 'resumen'

        for payslip in payslips:
            emp = payslip.employee_id
            company_id = payslip.company_id.id
            company_name = payslip.company_id.name
            grupo_poliza = emp.job_id.xs_tipo_grupo_poliza
            lineas = []
            for line in payslip.line_ids:
                if not line.appears_on_payslip or not line.total:
                    continue
                cuenta = ''
                cargo = 0
                abono = 0
                percepcion = False

                if line.salary_rule_id.tipo_id.id == p_id:
                    # Percepcion
                    cuenta = line.salary_rule_id.account_debit and line.salary_rule_id.account_debit.code or ''
                    cargo = line.total
                    percepcion = True

                elif line.salary_rule_id.tipo_id.id == d_id:
                    # Deduccion
                    cuenta = line.salary_rule_id.account_credit and line.salary_rule_id.account_credit.code or ''
                    abono = line.total

                elif line.salary_rule_id.tipo_id.id == o_id:
                    # Otros
                    if line.code == 'D100':  # SUBSIDIO PARA EL EMPLEO':
                        # Subsidio se pasa en negativo en el lado de deducciones (abono)
                        cuenta = line.salary_rule_id.account_credit and line.salary_rule_id.account_credit.code or ''
                        abono = -line.total
                    else:
                        cuenta = line.salary_rule_id.account_debit and line.salary_rule_id.account_debit.code or ''
                        cargo = line.total


                # Ajuste para Ofix
                """
                Checar si la cuenta comienza por 51X6 que se vaya a ventas dependiendo la que este configurada, 
                si no que se vaya a admistracion cmbiando el 6 x 7.
                Aplica TODAS las reglas cuya cuenta comienzan con 51*
                
                Evaluar el tipo de puesto del asociado y si es ventas se queda la cuenta que trae la regla salarial
                si es admvo hay que hacer la sustitución del 6 x 7
                """
                if percepcion and cuenta[:2] == '51' and len(cuenta) > 3:
                    cuenta = list(cuenta)
                    if grupo_poliza == 'administracion':
                        cuenta[3] = '7'
                    elif grupo_poliza == 'ventas':
                        cuenta[3] = '6'
                    cuenta = ''.join(cuenta)

                linea = [
                        '01',  # CIA Siempre será 01
                        cuenta,  # Cuenta
                        '000',  # Depto  Siempre sera 000
                        emp.company_id.x_id_almacen or '',  # Agregado con Studio por Jaime de OFIX
                        idregion_dict.get(emp.company_id.x_id_region, ''),  # Agregado con Studio por Jaime de OFIX
                        '0000',  # Linea  Siempre debera ser 0000
                        emp.barcode,  # Asoc
                        cargo,  # Cargo
                        abono,  # Abono
                    ]

                # Registra totales de cargos y abono por company
                self.add_to_dict_subs(company_id, data_dict_sub, cargo, abono)

                # Campo y agregado con Studio por Jaime OFIX
                agrupar_x_regla = bool(line.salary_rule_id.x_nivel_poliza == 'resumen')
                if agrupar_x_regla:
                    # Las lineas marcadas para agrupar 'resumen', por cuenta y grupo poliza se dejan para después
                    key = company_id, cuenta
                    if percepcion:
                        # Jaime: al separar por grupo_poliza, solo aplica para percepciones
                        key = company_id, cuenta, grupo_poliza

                    if key not in resumen_poliza_dict:
                        resumen_poliza_dict[key] = {
                            'company_id': company_id,
                            'company_name': company_name,
                            'cuenta': cuenta,
                            'linea': linea
                        }
                    else:
                        resumen_poliza_dict[key]['linea'][7] += cargo
                        resumen_poliza_dict[key]['linea'][8] += abono

                    # Asociado Cuando sea resumen en el nivel de la regla debera ser siempre asociado 1
                    resumen_poliza_dict[key]['linea'][6] = '1'

                else:
                    lineas.append(linea)

                if not cuenta:
                    if cargo:
                        self.avisos += 'Regla {} No tiene configurada cuenta deudora\n'.format(line.salary_rule_id.code)
                    else:
                        self.avisos += 'Regla {} No tiene configurada cuenta acreedora\n'.format(
                            line.salary_rule_id.code)

            # Agrega a diccionario las lineas de acuerd a los agrupamientos company
            self.add_to_dict(payslip.company_id.id, payslip.company_id.name, data_dict, lineas)

        # Agrega en el diccionario las lineas que fueron agrupadas por regla y depto
        for k, v in resumen_poliza_dict.items():
            self.add_to_dict(v.get('company_id'), v.get('company_name'),  data_dict, [v.get('linea', [])])

        data_list = []
        for k, v in data_dict.items():
            # k es Por company
            lineas = v.get('lineas', [])

            # Sumatoria cargos y abonos por cada company
            l2 = data_dict_sub.get(k)
            tcargo = l2.get('tcargo', 0)
            tabono = l2.get('tabono', 0)
            tabono = tcargo - tabono

            """
            CUENTA
            CASO 1: Para los totales de "cada método de pago ?" la cuenta será siempre la cuenta 210601004
            """
            lineas.append([
                # '01-{}'.format(k2),  # CIA
                '01',  # CIA
                '210601004',  # Cuenta
                '000',  # Depto
                '0000',  # Almacen
                '0000',  # Region
                '0000',  # Linea
                '1',  # Asociado Cuando sea resumen en el nivel de la regla debera ser siempre asociado 1
                0,  # Cargo
                tabono,  # Abono
            ])

            data_list.append({
                'name': v.get('name'),
                'header': head,
                'lineas': lineas,
            })

        return data_list

    @api.model
    def add_to_dict(self, company_id, company_name, data_dict, lineas):
        # Agrega a diccionario las lineas de acuerd a los agrupamientos company y tipo cuenta

        if not lineas or not len(lineas):
            return
        if not data_dict.get(company_id):
            # Agrupar por company
            data_dict[company_id] = {
                'name': company_name,
                'lineas': lineas,
            }
        else:
            data_dict[company_id]['lineas'] += lineas

    @api.model
    def add_to_dict_subs(self, company_id, data_dict_sub, cargo, abono):
        # Registra totales de cargos y abono por company
        if company_id not in data_dict_sub:
            data_dict_sub[company_id] = {
                    'tcargo': cargo,
                    'tabono': abono,
            }
        else:
            data_dict_sub[company_id]['tcargo'] += cargo
            data_dict_sub[company_id]['tabono'] += abono
