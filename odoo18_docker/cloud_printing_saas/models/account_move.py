from odoo import models, fields, api
from dateutil.relativedelta import relativedelta

class AccountMove(models.Model):
    _inherit = 'account.move'

    def _post(self, soft=True):
        """
        Extend license expiration when a subscription invoice is posted/paid.
        """
        res = super(AccountMove, self)._post(soft=soft)
        
        for move in self.filtered(lambda m: m.move_type == 'out_invoice'):
            # Trace back to Sales Orders linked to this invoice
            # sale_line_ids is the link from account.move.line to sale.order.line
            sale_orders = move.invoice_line_ids.mapped('sale_line_ids.order_id')
            
            for order in sale_orders:
                # Find the license linked to this subscription order
                license_rec = self.env['saas.license'].search([
                    ('subscription_id', '=', order.id)
                ], limit=1)
                
                if license_rec:
                    # Determine extension duration from the invoice lines
                    # We assume the invoice covers 1 period.
                    # We look for lines that have a recurring interval logic (if available) 
                    # OR we just default to the Subscription Order's logic.
                    
                    interval = 1
                    unit = 'month'
                    
                    # Try to find specific recurring info on the order lines
                    for line in order.order_line:
                          if hasattr(line, 'recurring_interval') and line.recurring_interval:
                               interval = line.recurring_interval
                               unit = line.recurring_unit or 'month'
                               break
                    
                    # Calculate new date
                    # Start from: current expiration OR today (whichever is later)
                    base_date = license_rec.expiration_date or fields.Date.today()
                    if base_date < fields.Date.today():
                        base_date = fields.Date.today()
                        
                    next_date = base_date
                    if unit == 'day':
                         next_date += relativedelta(days=interval)
                    elif unit == 'week':
                         next_date += relativedelta(weeks=interval)
                    elif unit == 'month':
                         next_date += relativedelta(months=interval)
                    elif unit == 'year':
                         next_date += relativedelta(years=interval)
                    
                    license_rec.expiration_date = next_date
                    
                    # Notify
                    license_rec.message_post(body=f"License extended until {next_date} via Invoice {move.name}")
                    
        return res
