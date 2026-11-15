/** Nombres cortos para los tipos que genera openapi-typescript desde /openapi.json (npm run tipos). */
import type { components } from "../api/esquema";

type S = components["schemas"];
export type Rol = S["LoginOut"]["rol"];
export type Delito = S["ResumenDistritoOut"]["target"];
export type Periodo = S["ResumenDistritoOut"]["periodo"];
export type Distrito = S["DistritoOut"];
export type Resumen = S["ResumenDistritoOut"];
export type Serie = S["SerieOut"];
export type Tabla = S["TablaOut"];
export type Ficha = S["FichaOut"];
export type Comparacion = S["ComparacionOut"];
export type Trazabilidad = S["TrazabilidadOut"];
export type Version = S["VersionResumenOut"];
export type VersionDetalle = S["VersionDetalleOut"];
export type Pendiente = S["PendienteOut"];
export type Ejecucion = S["EjecucionOut"];
export type Usuario = S["UsuarioOut"];
export type Estrategia = S["ErrorEstrategiaOut"]["estrategia"];
