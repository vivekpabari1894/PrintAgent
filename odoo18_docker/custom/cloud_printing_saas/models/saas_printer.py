from odoo import models, fields

class SaasPrinter(models.Model):
    _name = "saas.printer"
    _description = "SaaS Registered Printer"

    name = fields.Char(required=True)
    uid = fields.Char(string="OS Printer ID", required=True)
    server_uid = fields.Char(string="Agent ID", required=True)
    license_id = fields.Many2one("saas.license", string="License", required=True, ondelete="cascade")
    partner_id = fields.Many2one(related="license_id.partner_id", store=True)
    last_poll = fields.Datetime(string="Last Seen")

    _sql_constraints = [
        ('server_printer_uniq', 'unique(server_uid, uid, license_id)', 'Printer UID must be unique per Agent per License.')
    ]
