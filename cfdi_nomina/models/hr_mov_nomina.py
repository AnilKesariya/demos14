from odoo import api, models, fields

import logging
_logger = logging.getLogger(__name__)


class HrMovNomina(models.Model):
    _name = 'hr.mov.nomina'
    _description = 'Payroll movements pre-configured'
    _rec_name = 'name'

    name = fields.Char('Name', required=True)
    rule_id = fields.Many2one('hr.salary.rule', 'Salary Rule', required=True)
    rule_code = fields.Char(related='rule_id.code', type="char", string="Code", readonly=True)
    amount_python_compute = fields.Text('Formula')
    state = fields.Selection([('alta', 'Alta'), ('baja', 'Baja')], string='Status', default='baja')
    mov_nomina_lines = fields.One2many('hr.mov.nomina.line', 'mov_nomina_id', string='Employees', required=True)

    
    def action_baja(self):
        self.state = 'baja'

    
    def action_alta(self):
        self.state = 'alta'

    
    def action_vaciar(self):
        for elemento in self:
            if elemento.state == 'alta' or not elemento.mov_nomina_lines:
                continue
            elemento.mov_nomina_lines.unlink()
            elemento.mov_nomina_lines = []


class HrMovNominaLinea(models.Model):
    _name = 'hr.mov.nomina.line'
    _description = 'Payroll Movement Lines pre-configured'

    mov_nomina_id = fields.Many2one('hr.mov.nomina')
    employee_id = fields.Many2one('hr.employee', 'Employee', required=True)
    amount_python_compute = fields.Text('Formula')
    date_deadline = fields.Date('Deadline')
