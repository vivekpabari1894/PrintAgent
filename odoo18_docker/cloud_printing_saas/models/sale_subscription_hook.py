from odoo import models, fields, api, _

class SaleSubscription(models.Model):
    _inherit = "sale.subscription"

    def write(self, vals):
        res = super(SaleSubscription, self).write(vals)
        for sub in self:
            # Check for stage change using the related field 'stage_type'
            # Note: stage_type is related to stage_id.type
            if sub.stage_type == 'in_progress':
                sub._ensure_saas_license()
            elif sub.stage_type == 'post': # Closed
                sub._cancel_saas_license()
        return res

    def generate_invoice(self):
        # Hook: When invoice is generated, it means renewal (or initial).
        # We process this to extend the license.
        res = super(SaleSubscription, self).generate_invoice()
        
        for sub in self:
            # Only extend if we have an active license and still in progress
            if sub.in_progress:
                sub._extend_saas_license()
        return res

    def _ensure_saas_license(self):
        """
        Creates a license if missing, or activates existing one.
        """
        License = self.env['saas.license']
        license_rec = License.search([
            ('recurring_subscription_id', '=', self.id)
        ], limit=1)
        
        if not license_rec:
            # Fix 2: Link to Sale Order Source
            sale_order = self.env['sale.order']
            if self.sale_order_ids:
                sale_order = self.sale_order_ids[0]
                
            # Try to match by Partner to avoid dupes?
            # Or just create new one linked to this contract.
            license_rec = License.create({
                'partner_id': self.partner_id.id,
                'recurring_subscription_id': self.id,
                'subscription_id': sale_order.id, # Set original SO
                'active': True,
                'state': 'active'
            })
            
            # Fix 3: Send Email Notification to Customer
            # We construct a simple subject/body. Ideally use a template.
            subject = _("Your Cloud Printing License Key")
            body = _("Dear %s,<br/><br/>Your Cloud Printing License has been generated.<br/><b>License Key: %s</b><br/><br/>You can configure this in your Odoo Settings.<br/>Expiration: %s") % (self.partner_id.name, license_rec.name, self.recurring_next_date or 'N/A')
            
            self.message_post(
                body=body,
                subject=subject,
                message_type='comment',
                subtype_xmlid='mail.mt_comment',
                partner_ids=[self.partner_id.id]
            )
            # Also post on the license itself
            license_rec.message_post(body="License created automatically from Subscription.")
        
        # Ensure it is active
        if not license_rec.active:
            license_rec.active = True
        
        # Sync expiration with Next Invoice Date
        if self.recurring_next_date:
            license_rec.expiration_date = self.recurring_next_date

    def _extend_saas_license(self):
        """
        Called when invoice is generated. Extends the license date.
        """
        License = self.env['saas.license']
        license_rec = License.search([
            ('recurring_subscription_id', '=', self.id)
        ], limit=1)
        
        if license_rec:
            # If recurring_next_date was just updated by generate_invoice, rely on it.
            if self.recurring_next_date:
                license_rec.expiration_date = self.recurring_next_date
                license_rec.state = 'active' # Reactivate if it was expired
                
    def _cancel_saas_license(self):
        """
        Deactivate license when subscription closes.
        """
        License = self.env['saas.license']
        license_rec = License.search([
            ('recurring_subscription_id', '=', self.id)
        ], limit=1)
        if license_rec:
            license_rec.active = False
            license_rec.state = 'cancelled'
            self.message_post(body=f"SaaS License {license_rec.name} Deactivated.")
