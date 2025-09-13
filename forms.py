from flask_wtf import FlaskForm
from wtforms import (
    StringField, PasswordField, DecimalField, IntegerField,
    SubmitField, FileField, BooleanField
)
from wtforms.validators import DataRequired, NumberRange, Length, Optional


class LoginForm(FlaskForm):
    email = StringField("Email", validators=[DataRequired(), Length(max=255)])
    password = PasswordField("Password", validators=[DataRequired()])
    submit = SubmitField("Sign In")


class ItemForm(FlaskForm):
    sku = StringField("Item Number (SKU)", validators=[DataRequired(), Length(max=100)])
    name = StringField("Item Name", validators=[DataRequired(), Length(max=200)])
    price = DecimalField("Price", places=4, rounding=None,
                         validators=[Optional(), NumberRange(min=0)])

    on_hand = IntegerField("On-hand Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    on_transit = IntegerField("On-transit Quantity", validators=[Optional(), NumberRange(min=0)], default=0)
    reorder_point = IntegerField("Reorder Point", validators=[Optional(), NumberRange(min=0)], default=0)

    submit = SubmitField("Save")


class ImportForm(FlaskForm):
    file = FileField("CSV File", validators=[DataRequired()])
    dry_run = BooleanField("Dry run (preview only)", default=True)
    replace = BooleanField("Replace all existing items (dangerous)")
    submit = SubmitField("Upload")
