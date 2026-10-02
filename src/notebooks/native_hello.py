# Databricks notebook source
dbutils.widgets.text("greeting", "")
dbutils.widgets.text("bundle_target", "")

greeting = dbutils.widgets.get("greeting").strip()
bundle_target = dbutils.widgets.get("bundle_target").strip()

if not greeting:
    raise ValueError("El parámetro 'greeting' no puede estar vacío.")

if bundle_target != "sandbox":
    raise ValueError(
        f"Este laboratorio solo puede ejecutarse en sandbox; recibido: {bundle_target!r}"
    )

marker = f"BUNDLE_LAB_OK|target={bundle_target}|message={greeting}"
print(marker)
dbutils.notebook.exit(marker)
