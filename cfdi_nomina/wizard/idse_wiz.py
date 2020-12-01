import logging
from odoo.exceptions import ValidationError, UserError
import datetime
import logging
from dateutil import relativedelta
import base64
import unicodedata
from odoo.tools import ustr

from odoo import api, models, fields

_logger = logging.getLogger(__name__)


def remove_accents(input_str):
    ''' Remove all the accented characters from a string
    :param input_str str(P3)/unicode(P2): A text that may contain accents.
    :return: The same text with the accented characters mapped to their
             "unaccented" counterpart.
    :rtype: str (P3) or unicode (P2)
    '''
    nfkd_form = unicodedata.normalize('NFKD', input_str)
    only_ascii = nfkd_form.encode('ASCII', 'ignore').decode('utf-8')
    return only_ascii


class HrIDSECWiz(models.TransientModel):
    _name = 'hr.idsec.wiz'
    _description = 'Wizard para Generar IDSE Carvajal'

    company_ids = fields.Many2many('res.company', string='Companies')
    date_from = fields.Date('Initial Date', required=True,
                            default=(datetime.datetime.now() + relativedelta.relativedelta(days=-1)))
    date_to = fields.Date('Ending Date', required=True, default=datetime.datetime.now())
    bimestre = fields.Selection([('bim_anterior', 'Bimestre Anterior'), ('bim_actual', 'Bimestre Actual')],
                                string="Bimonthly", default="bim_anterior", required=True)
    data_file = fields.Binary('File generated', filters='*.csv,*.txt', readonly=True)
    data_fname = fields.Char('File Name')
    avisos = fields.Text('Notices', readonly=1, default='')
    state = fields.Selection([('draft', 'Nuevo'), ('done', 'Terminado')], default='draft')
    tipo = fields.Selection([
        ('modifcaciones', 'Modificaciones'),
        ('altas', 'Altas/Reingresos'),
        ('bajas', 'Bajas'),
    ], default='modifcaciones', required=True, string="Tipo")
    guia = fields.Char(default='400')
    umf = fields.Char("UMF", default='000')
    mensaje = fields.Text('Message', readonly=True)

    @api.onchange('tipo')
    def onchange_tipo(self):
        if self.tipo != 'modifcaciones':
            self.bimestre = 'bim_anterior'

    def gen_idse(self):
        if self.date_from > self.date_to:
            raise ValidationError('Fecha de inicio debe anteceder a fecha final')

        idse_txt = ''
        fname = '{}-IDSE.txt'.format(fields.Date.today())

        if self.tipo == 'altas':
            idse_txt = self.get_altas()
            fname = '{}-IDSE-ALTAS.txt'.format(fields.Date.today())
        elif self.tipo == 'bajas':
            idse_txt = self.get_bajas()
            fname = '{}-IDSE-BAJAS.txt'.format(fields.Date.today())
        elif self.tipo == 'modifcaciones':
            if self.bimestre == 'bim_actual':
                idse_txt = self.get_mod_actual()
            else:
                idse_txt = self.get_mod()

            fname = '{}-IDSE-MOD.txt'.format(fields.Date.today())

        self.write({
            'data_file': base64.encodebytes(idse_txt.encode('utf8')),
            'data_fname': fname,
            'state': 'done',
        })

        return {
            'type': 'ir.actions.act_window',
            'name': 'IDSE Generado',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': self._name,
            'res_id': self.id,
            'target': 'new',
        }

    def get_altas(self):

        idse_txt = ''
        domain = [
            ('fecha_alta', '>=', self.date_from),
            ('fecha_alta', '<=', self.date_to),
        ]
        if self.company_ids:
            domain.append(('company_id', 'in', self.company_ids.ids))
        mov_altas = self.env['hr.employee'].search(domain)
        if not mov_altas:
            raise ValidationError('No hay datos entre las fechas dadas')

        contract_obj = self.env['hr.contract']
        mensaje = ''

        for e in mov_altas:
            contrato = contract_obj.search([('employee_id', '=', e.id), ('state', '=', 'open')], limit=1)
            if not contrato:
                mensaje += 'NO se localizó contrato para empleado {}\n'.format(e.cod_emp)
                continue

            # tipo_trab = 2   # 1: permanente, 2: Eventual Ciudad, 3: Eventual Construcc, 4: Eventual Campo
            # if contrato.type_id.code in ['01']:
            #     tipo_trab = 1
            tipo_trab = 1

            tipo_salario = 2   # 0: fijo, 1: Variable, 2: Mixto
            if e.tipo_sueldo == 'fijo':
                tipo_salario = 0
            elif e.tipo_sueldo == 'variable':
                tipo_salario = 1
            jornada = 0    # 1-5: dias, 6: Jornada reducida, 0: Jornada normal
            tipo_mov = 8   # 06: Alta,  08: Reingreso
            if e.status_imss == 'alta':
                tipo_mov = 6

            line = "{rpatronal:>11.11}{nss:>11.11}" \
                   "{appat:<27.27}{apmat:<27.27}{nombres:<27.27}{sdi:06.2f}{sdinf:06.2f}" \
                   "{tipo_trab:1.1}{tipo_salario:1.1}{jornada:1.1}{fecha:8.8}{umf:>3.3}" \
                   "{space:2.1}{tipo_mov:02.1}{guia:>5.5}{clave_trab:>10.10}" \
                   "{space:1.1}{curp:>18.18}{idf:1.1}{folio_incapacidad:>8.8}{ndias:2.1}{sucursal:03.1}" \
                   "\r\n".format(
                rpatronal=e.registro_patronal and e.registro_patronal.name or ' ',
                nss=e.imss or '',
                appat=e.appat or '',
                apmat=e.apmat or '',
                nombres=e.name or '',
                sdi=e.sueldo_imss,
                sdinf=e.sueldo_imss,   # e.sueldo_info,
                space=' ',
                tipo_trab=float(tipo_trab),
                tipo_salario=float(tipo_salario),
                jornada=float(jornada),
                fecha=datetime.datetime.strptime(str(e.fecha_alta), '%Y-%m-%d').strftime("%d%m%Y"),
                umf=self.umf,
                tipo_mov=float(tipo_mov),
                guia=self.guia,
                clave_trab=float(e.cod_emp),
                curp=str(e.curp),
                idf=float(9),
                folio_incapacidad='',
                ndias = ' ',
                sucursal = float(0)
            )

            idse_txt += remove_accents(line.replace(u'ñ', '#').replace(u'Ñ', '#'))

        self.mensaje = mensaje

        return idse_txt

    def get_bajas(self):

        idse_txt = ''
        domain = [
            ('fecha_baja', '>=', self.date_from),
            ('fecha_baja', '<=', self.date_to),
        ]
        if self.company_ids:
            domain.append(('company_id', 'in', self.company_ids.ids))
        mov_bajas = self.env['hr.employee'].search(domain)


        if not mov_bajas:
            raise ValidationError('No hay datos entre las fechas dadas')

        mensaje = ''

        for e in mov_bajas:

            # causa_baja 1) Termino de contrato, 2) Separación voluntaria, 3) Abandono de empleo, 4)Defunción,
            # 5) Clausura, 6) Otras, 7) Ausentismo, 8) Rescisión de contrato, 9) Jubilación, A) Pensión
            causa_baja = e.causa_baja

            if not causa_baja:
                mensaje += 'Debe establecer una causa de baja del empleado numero {}, dia {} \n'.format(
                    e.cod_emp, e.fecha_baja
                )
                continue

            tipo_mov = 2    # 02: baja

            # para el caso de asociados que tengan  un punto en el apellido paterno o materno
            # se tendrá que sustituir por dos espacios
            appat = (e.appat or '').replace('.', '  ')
            apmat = (e.apmat or '').replace('.', '  ')
            nombres = (e.name or '').replace('.', '  ')

            line = "{rpatronal:>11.11}{nss:>11.11}" \
                   "{appat:<27.27}{apmat:<27.27}{nombres:<27.27}{space:15}" \
                   "{fecha:8.8}{generico:05}" \
                   "{tipo_mov:02}{space:5}{clave_trab:>10.10}" \
                   "{causa_baja:1}{curp:>18.18}{idf:1}{folio_incapacidad:>8.8}{ndias:2}{sucursal:03}" \
                   "\r\n".format(
                rpatronal=e.registro_patronal and e.registro_patronal.name or ' ',
                nss=e.imss or '',
                appat=appat,
                apmat=apmat,
                nombres=nombres,
                space=' ',
                fecha=datetime.datetime.strptime(str(e.fecha_baja), '%Y-%m-%d').strftime("%d%m%Y"),
                generico=float(0),
                umf=self.umf,
                tipo_mov=float(tipo_mov),
                clave_trab=str(e.cod_emp),
                causa_baja=causa_baja,
                curp=str(e.curp),
                idf=float(9),
                folio_incapacidad='',
                ndias=' ',
                sucursal=float(0)
            )

            idse_txt += remove_accents(line.replace(u'ñ', '#').replace(u'Ñ', '#'))
        self.mensaje = mensaje

        return idse_txt

    def get_mod(self):

        idse_txt = ''
        domain = [
            ('name', '>=', self.date_from),
            ('name', '<=', self.date_to),
            ('employee_id.active', '=', True),
        ]
        if self.company_ids:
            domain.append(('employee_id.company_id', 'in', self.company_ids.ids))
        mov_sdi = self.env['hr.employee.historico.imss'].search(domain)
        if not mov_sdi:
            raise ValidationError('No hay datos entre las fechas dadas')

        contract_obj = self.env['hr.contract']
        mensaje = ''

        for mov in mov_sdi:

            e = mov.employee_id
            contrato = contract_obj.search([('employee_id', '=', e.id), ('state', '=', 'draft')], limit=1)
            if not contrato:
                mensaje += 'NO se localizó contrato para empleado {}\n'.format(e.cod_emp)
                continue

            # tipo_trab = 2   # 1: permanente, 2: Eventual Ciudad, 3: Eventual Construcc, 4: Eventual Campo
            # if contrato.type_id.code in ['01']:
            #     tipo_trab = 1
            tipo_trab = 1

            tipo_salario = 2  # 0: fijo, 1: Variable, 2: Mixto
            if e.tipo_sueldo == 'fijo':
                tipo_salario = 0
            elif e.tipo_sueldo == 'variable':
                tipo_salario = 1
            tipo_mov = 7     # 07: modif salario

            # para empleados que tengan 6 digitos o mas se tendra que quitar el punto dejando la cantidad plana
            sdi = mov.sueldo_new
            if sdi > 999.99:
                sdi = "{:06.0f}".format(sdi * 100.0)
            else:
                sdi = "{:06.2f}".format(sdi)

            sdinf = mov.sueldo_new
            if sdinf > 999.99:
                sdinf = "{:06.0f}".format(sdinf * 100.0)
            else:
                sdinf = "{:06.2f}".format(sdinf)

            # para el caso de asociados que tengan  un punto en el apellido paterno o materno
            # se tendrá que sustituir por dos espacios
            appat = (e.appat or '').replace('.', '  ')
            apmat = (e.apmat or '').replace('.', '  ')
            nombres = (e.name or '').replace('.', '  ')

            # line = "{rpatronal:>11.11}{nss:>11.11}" \
            #        "{appat:<27.27}{apmat:<27.27}{nombres:<27.27}{sdi:>6}{sdinf:>6}" \
            #        "{tipo_trab:1}{tipo_salario:1}{jornada:1}{fecha:8.8}" \
            #        "{space:5}{tipo_mov:02}{guia:>5.5}{clave_trab:>10.10}" \
            #        "{space:1}{curp:>18.18}{idf:1}{folio_incapacidad:>8.8}{ndias:2}{sucursal:03}" \
            #        "\r\n".format(
            #     rpatronal=e.registro_patronal and e.registro_patronal.name or ' ',
            #     nss=e.imss or '',
            #     appat=appat,
            #     apmat=apmat,
            #     nombres=nombres,
            #     sdi=sdi,
            #     sdinf=sdinf,
            #     space=' ',
            #     tipo_trab=tipo_trab,
            #     tipo_salario=tipo_salario,
            #     jornada=0,
            #     fecha=datetime.datetime.strptime(str(mov.name), '%Y-%m-%d').strftime("%d%m%Y"),
            #     tipo_mov=tipo_mov,
            #     guia=self.guia,
            #     clave_trab=e.cod_emp,
            #     curp=e.curp,
            #     idf=9,
            #     folio_incapacidad='',
            #     ndias=' ',
            #     sucursal=0
            # )

            line = "{rpatronal:>11}{nss:>11}" \
                   "{appat:<27}{apmat:<27}{nombres:<27}{sdi:>6}{sdinf:>6}" \
                   "{tipo_trab:1}{tipo_salario:1}{jornada:1}{fecha:8}" \
                   "{space:5}{tipo_mov:02}{guia:>5.5}{clave_trab:>10}" \
                   "{space:1}{curp:>18}{idf:1}{folio_incapacidad:>8}{ndias:2}{sucursal:03}" \
                   "\r\n".format(
                rpatronal=e.registro_patronal and e.registro_patronal.name or ' ',
                nss=e.imss or '',
                appat=appat,
                apmat=apmat,
                nombres=nombres,
                sdi=sdi,
                sdinf=sdinf,
                space=' ',
                tipo_trab=tipo_trab,
                tipo_salario=tipo_salario,
                jornada=0,
                fecha=datetime.datetime.strptime(str(mov.name), '%Y-%m-%d').strftime("%d%m%Y"),
                tipo_mov=tipo_mov,
                guia=self.guia,
                clave_trab=e.cod_emp,
                curp=str(e.curp),
                idf=9,
                folio_incapacidad='',
                ndias=' ',
                sucursal=0
            )

            idse_txt += remove_accents(line.replace(u'ñ', '#').replace(u'Ñ', '#'))

        self.mensaje = mensaje

        return idse_txt

    def get_mod_actual(self):

        # En sueldo bimestral del empleado esta el ultimo sueldo bimestral
        idse_txt = ''
        domain = [
            ('sueldo_imss_bimestre_actual', '>', 0),
        ]
        if self.company_ids:
            domain.append(('company_id', 'in', self.company_ids.ids))
        emp_sdi_bim = self.env['hr.employee'].search(domain)
        if not emp_sdi_bim:
            raise ValidationError('No hay empleados con ultimo sueldo IMSS bimestral actual registrado')

        contract_obj = self.env['hr.contract']
        mensaje = ''

        for e in emp_sdi_bim:

            contrato = contract_obj.search([('employee_id', '=', e.id), ('state', '=', 'open')], limit=1)
            if not contrato:
                mensaje += 'NO se localizó contrato para empleado {}\n'.format(e.cod_emp)
                continue

            # tipo_trab = 2   # 1: permanente, 2: Eventual Ciudad, 3: Eventual Construcc, 4: Eventual Campo
            # if contrato.type_id.code in ['01']:
            #     tipo_trab = 1
            tipo_trab = 1

            tipo_salario = 2  # 0: fijo, 1: Variable, 2: Mixto
            if e.tipo_sueldo == 'fijo':
                tipo_salario = 0
            elif e.tipo_sueldo == 'variable':
                tipo_salario = 1
            tipo_mov = 7  # 07: modif salario

            # para empleados que tengan 6 digitos o mas se tendra que quitar el punto dejando la cantidad plana
            sdi = e.sueldo_imss_bimestre_actual
            if sdi > 999.99:
                sdi = "{:06.0f}".format(sdi*100.0)
            else:
                sdi = "{:06.2f}".format(sdi)

            sdinf = e.sueldo_imss_bimestre_actual  # e.sueldo_info
            if sdinf > 999.99:
                sdinf = "{:06.0f}".format(sdinf*100.0)
            else:
                sdinf = "{:06.2f}".format(sdinf)

            # para el caso de asociados que tengan  un punto en el apellido paterno o materno
            # se tendrá que sustituir por dos espacios
            appat = (e.appat or '').replace('.', '  ')
            apmat = (e.apmat or '').replace('.', '  ')
            nombres = (e.name or '').replace('.', '  ')

            line = "{rpatronal:>11.11}{nss:>11.11}" \
                   "{appat:<27.27}{apmat:<27.27}{nombres:<27.27}{sdi:>6}{sdinf:>6}" \
                   "{tipo_trab:1}{tipo_salario:1}{jornada:1}{fecha:8.8}" \
                   "{space:5}{tipo_mov:02}{guia:>5.5}{clave_trab:>10.10}" \
                   "{space:1}{curp:>18.18}{idf:1}{folio_incapacidad:>8.8}{ndias:2}{sucursal:03}" \
                   "\r\n".format(
                rpatronal=e.registro_patronal and e.registro_patronal.name or ' ',
                nss=e.imss or '',
                appat=appat,
                apmat=apmat,
                nombres=nombres,
                sdi=sdi,
                sdinf=sdinf,
                space=' ',
                tipo_trab=tipo_trab,
                tipo_salario=tipo_salario,
                jornada=0,
                fecha=datetime.datetime.strptime(str(self.date_from), '%Y-%m-%d').strftime("%d%m%Y"),
                tipo_mov=tipo_mov,
                guia=self.guia,
                clave_trab=str(e.cod_emp),
                curp=str(e.curp),
                idf=float(9),
                folio_incapacidad='',
                ndias=' ',
                sucursal=float(0)
            )

            #  las Ñ las ponga como carácter #
            idse_txt += remove_accents(line.replace(u'ñ', '#').replace(u'Ñ', '#'))

        self.mensaje = mensaje

        return idse_txt
