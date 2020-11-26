# -*- coding: utf-8 -*-
from openerp.osv import osv, fields
import base64


class reporte_acumulado(osv.TransientModel):
    _name = "cfdi_nomina.reporte.acumulado"
    _description = 'aggregate report'

    _columns = {
        'fecha_inicio': fields.date("Start date"),
        'fecha_fin': fields.date("End date"),
        # 'period_id': fields.many2one("account.period", "Periodo", required=True), #reemplaza a fecha inicio y fecha fin
        'nominas': fields.many2many("hr.payslip.run", string=u"Payslip", required=True),
        # ya no se usará, ahora es por agrupación
        'rule_ids': fields.many2many("hr.salary.rule", string="Rules"),
        'rule_group_ids': fields.many2many("hr.salary.rule.group", string="Groupings"),
        'employee_ids': fields.many2many("hr.employee", string="Employees"),
        'datas': fields.binary("Reporte CSV"),
        'fname': fields.char("Fname")
    }

    def action_reporte_acumulado(self, cr, uid, ids, context=None):
        data, line_ids = self._create_report(cr, uid, ids, context=context)
        this = self.browse(cr, uid, ids[0])
        view_id = self.pool.get("ir.model.data").get_object(
            cr, uid, 'cfdi_nomina', 'reporte_acumulado_line_view').id
        return {
            'name': 'Reporte del periodo %s' % (this.period_id.name),
            'type': 'ir.actions.act_window',
            'res_model': "cfdi_nomina.reporte.acumulado.line",
            'view_type': "form",
            'view_mode': 'list',
            'context': context,
            'view_id': view_id,
            'domain': [('id', 'in', line_ids)]
        }

    def action_reporte_excel(self, cr, uid, ids, context=None):
        this = self.browse(cr, uid, ids[0])
        data, line_ids = self._create_report(cr, uid, ids, context=context)
        linea_nominas = " ".join([x.name for x in this.nominas])
        header = ["Empleado", "Cod. Emp.", "RFC", "IMSS"]
        for rule in this.rule_group_ids:
            header.append(rule.name)
        header.extend(["Otras percepciones", "Otras deducciones",
                       "Gravado", "Exento", "Neto"])
        rows = []
        employee_obj = self.pool.get("hr.employee")
        for line in data:
            name = employee_obj.browse(
                cr, uid, line["employee_id"]).nombre_completo
            row = [name, line["codemp"], line["rfc"], line["imss"]]
            for rule in this.rule_group_ids:
                row.append(line.get("rule_group_%s" % rule.id, 0))
            row.extend([line["p_otras"], line["d_otras"], line[
                       "gravado"], line["exento"], line["neto"]])
            rows.append(row)
        csv_data = linea_nominas + "\n"
        csv_data += ",".join(header) + "\n"
        for row in rows:
            _row = []
            for x in row:
                if type(x) != unicode and type(x) != str:
                    _row.append(str(x))
                else:
                    _row.append(x)
            csv_data += ",".join([x.replace(",", " ") for x in _row]) + "\n"
        datas = base64.b64encode(csv_data.encode("utf-8"))
        self.write(cr, uid, [this.id], {
                   'datas': datas, 'fname': 'Reporte acumulados %s.csv' % (this.period_id.name)})
        return {
            'name': 'Reporte acumulados',
            'type': 'ir.actions.act_window',
            'res_model': "cfdi_nomina.reporte.acumulado",
            'view_type': "form",
            'view_mode': 'form',
            'context': context,
            'res_id': this.id,
            'target': 'new'
        }

    def _create_report(self, cr, uid, ids, context=None):
        context = context or {}
        this = self.browse(cr, uid, ids[0])

        if not this.nominas:
            raise osv.except_osv("Warning", u"No se han seleccionado nóminas")

        rule_ids = [x.id for x in this.rule_group_ids]
        context["rule_ids"] = rule_ids
        employee_obj = self.pool.get("hr.employee")
        slip_line_obj = self.pool.get("hr.payslip.line")
        model_obj = self.pool.get("ir.model.data")
        PERCEPCION = model_obj.get_object(
            cr, uid, "cfdi_nomina", "catalogo_tipo_percepcion").id
        DEDUCCION = model_obj.get_object(
            cr, uid, "cfdi_nomina", "catalogo_tipo_deduccion").id
        # model_obj.get_object(cr, uid, "cfdi_nomina", "catalogo_tipo_hora_extra").id
        HORA_EXTRA = False
        INCAPACIDAD = model_obj.get_object(
            cr, uid, "cfdi_nomina", "catalogo_tipo_incapacidad").id

        if this.employee_ids:
            employee_ids = [x.id for x in this.employee_ids]
        else:
            cr.execute("select id from hr_employee")
            employee_ids = [row[0] for row in cr.fetchall()]

        line_obj = self.pool.get("cfdi_nomina.reporte.acumulado.line")
        line_ids = []
        data = []
        for employee in employee_obj.browse(cr, uid, employee_ids):
            vals = {
                'employee_id': employee.id,
                'codemp': employee.cod_emp,
                'rfc': employee.rfc,
                'imss': employee.imss,
            }
            slip_line_ids = slip_line_obj.search(cr, uid, [
                ('slip_id.payslip_run_id', 'in', [x.id for x in this.nominas]),
                ('employee_id', '=', employee.id)
            ])
            if not slip_line_ids:
                if len(this.employee_ids) > 0:
                    raise osv.except_osv(
                        "Warning", u"El empleado %s no está en las nóminas seleccionadas" % employee.nombre_completo)
                else:
                    continue
            neto = 0
            p_otras = 0
            d_otras = 0
            gravado = 0
            exento = 0
            rule_totals = {rid: 0 for rid in rule_ids}
            for slip_line in slip_line_obj.browse(cr, uid, slip_line_ids):
                tipo = slip_line.salary_rule_id.gravado_o_exento or 'gravado'
                if tipo == 'gravado':
                    gravado += slip_line.total
                elif tipo == 'exento':
                    exento += slip_line.total
                if slip_line.salary_rule_id.tipo_id.id in (PERCEPCION, HORA_EXTRA):
                    neto += slip_line.total
                if slip_line.salary_rule_id.tipo_id.id in (DEDUCCION, INCAPACIDAD):
                    neto -= slip_line.total
                if slip_line.salary_rule_id.agrupacion.id in rule_ids:
                    rule_totals[
                        slip_line.salary_rule_id.agrupacion.id] += slip_line.total
                    # vals.update({
                    #    "rule_group_%s"%slip_line.salary_rule_id.agrupacion.id: slip_line.total
                    #})
                else:
                    if slip_line.salary_rule_id.tipo_id.id in (PERCEPCION, HORA_EXTRA):
                        p_otras += slip_line.total
                    elif slip_line.salary_rule_id.tipo_id.id in (DEDUCCION, INCAPACIDAD):
                        d_otras += slip_line.total

            for rule_id, rule_total in rule_totals.iteritems():
                vals.update({"rule_group_%s" % rule_id: rule_total})

            vals.update({
                'neto': neto,
                'p_otras': p_otras,
                'd_otras': d_otras,
                'exento': exento,
                'gravado': gravado
            })
            data.append(vals)
            line_id = line_obj.create(cr, uid, vals)
            line_ids.append(line_id)

        return data, line_ids


class reporte_acumulado_line(osv.TransientModel):
    _name = "cfdi_nomina.reporte.acumulado.line"

    _columns = {
        'employee_id': fields.many2one("hr.employee", string="Employee"),
        'codemp': fields.integer("Cod. Emp."),
        'rfc': fields.char("RFC"),
        'imss': fields.char("IMSS"),
        'p_otras': fields.float("Other barnacles"),
        'd_otras': fields.float("Other Deductions"),
        'gravado': fields.float("Total taxed"),
        'exento': fields.float("Total exempt"),
        'neto': fields.float("Net")
    }

    def __init__(self, pool, cr):
        # Columnas por regla (ya no se usarán)
        cr.execute("select id from hr_salary_rule")
        for row in cr.fetchall():
            field_name = "rule_%s" % row[0]
            self._columns[field_name] = fields.float(field_name)
        # Columnas por agrupación
        cr.execute("select id from hr_salary_rule_group")
        for row in cr.fetchall():
            field_name = "rule_group_%s" % row[0]
            self._columns[field_name] = fields.float(field_name)

        return super(reporte_acumulado_line, self).__init__(pool, cr)

    def fields_view_get(self, cr, uid, view_id=None, view_type='form', context=None, toolbar=False, submenu=False):
        context = context or {}
        res = super(reporte_acumulado_line, self).fields_view_get(
            cr, uid, view_id=view_id, view_type=view_type, context=context, toolbar=toolbar, submenu=submenu)
        if view_type != "tree":
            return res
        import xml.etree.ElementTree as ET
        arch = res["arch"]
        root = ET.fromstring(arch)
        if 'rule_ids' in context:
            for rule in self.pool.get("hr.salary.rule.group").browse(cr, uid, context["rule_ids"]):
                root.insert(4, ET.XML('<field name="rule_group_%s" string="%s" sum="Total"/>' %
                                      (rule.id, rule.name.encode("utf-8"))))
        res["arch"] = ET.tostring(root, encoding="UTF-8")
        return res
