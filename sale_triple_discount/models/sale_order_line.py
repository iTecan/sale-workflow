# Copyright 2015 ADHOC SA  (http://www.adhoc.com.ar)
# Copyright 2017 - 2019 Alex Comba - Agile Business Group
# Copyright 2017 Tecnativa - David Vidal
# Copyright 2018 Simone Rubino - Agile Business Group
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    discount2 = fields.Float(
        string="Disc. 2 (%)",
        digits="Discount",
        default=0.0,
    )
    discount3 = fields.Float(
        string="Disc. 3 (%)",
        digits="Discount",
        default=0.0,
    )
    discounting_type = fields.Selection(
        selection=[("additive", "Additive"), ("multiplicative", "Multiplicative")],
        default="multiplicative",
        required=True,
        help="Specifies whether discounts should be additive "
        "or multiplicative.\nAdditive discounts are summed first and "
        "then applied.\nMultiplicative discounts are applied sequentially.\n"
        "Multiplicative discounts are default",
    )

    def _get_final_discount(self):
        self.ensure_one()
        if self.discounting_type == "additive":
            return self._additive_discount()
        elif self.discounting_type == "multiplicative":
            return self._multiplicative_discount()
        else:
            raise ValidationError(
                _("Sale order line %(name)s has unknown discounting type %(dic_type)s")
                % {"name": self.name, "disc_type": self.discounting_type}
            )

    def _additive_discount(self):
        self.ensure_one()
        discount = sum(self[x] or 0.0 for x in self._discount_fields())
        if discount <= 0:
            return 0
        elif discount >= 100:
            return 100
        return discount

    def _multiplicative_discount(self):
        self.ensure_one()
        discounts = [1 - (self[x] or 0.0) / 100 for x in self._discount_fields()]
        final_discount = 1
        for discount in discounts:
            final_discount *= discount
        return 100 - final_discount * 100

    @api.model
    def _discount_fields(self):
        return ["discount", "discount2", "discount3"]

    @api.depends("discount2", "discount3", "discounting_type")
    def _compute_amount(self):
        prev_values = self.triple_discount_preprocess()
        res = super()._compute_amount()
        self.triple_discount_postprocess(prev_values)
        return res

    _sql_constraints = [
        (
            "discount2_limit",
            "CHECK (discount2 <= 100.0)",
            "Discount 2 must be lower or equal than 100%.",
        ),
        (
            "discount3_limit",
            "CHECK (discount3 <= 100.0)",
            "Discount 3 must be lower or equal than 100%.",
        ),
    ]

    def _prepare_invoice_line(self, **kwargs):
        """
        Inherit this method to bring
        more discount fields to the invoice lines
        """
        res = super()._prepare_invoice_line(**kwargs)
        res.update({"discount2": self.discount2, "discount3": self.discount3})
        return res

    def triple_discount_preprocess(self):
        """Prepare data for post processing.

        Save the values of the discounts in a dictionary,
        to be restored in postprocess.
        Resetting every discount except the main one to 0.0 avoids issues if
        this method is called multiple times.
        Updating the cache provides consistency through re-computations."""
        prev_values = dict()
        self.invalidate_recordset(self._discount_fields())
        for line in self:
            prev_values[line] = {
                fname: line[fname] for fname in self._discount_fields()
            }

            vals = {fname: 0 for fname in self._discount_fields()}
            vals["discount"] = line._get_final_discount()

            line._cache.update(vals)
        return prev_values

    @api.model
    def triple_discount_postprocess(self, prev_values):
        """Restore the discounts of the lines in the dictionary prev_values.
        Updating the cache provides consistency through re-computations."""
        self.invalidate_recordset(self._discount_fields())
        for line, prev_vals_dict in list(prev_values.items()):
            line.update(prev_vals_dict)

    def _convert_to_tax_base_line_dict(self):
        self.ensure_one()
        return self.env["account.tax"]._convert_to_tax_base_line_dict(
            self,
            partner=self.order_id.partner_id,
            currency=self.order_id.currency_id,
            product=self.product_id,
            taxes=self.tax_id,
            price_unit=self.price_unit,
            quantity=self.product_uom_qty,
            discount=self._get_final_discount(),
            price_subtotal=self.price_subtotal,
        )
