import { Link, Route, Routes } from "react-router-dom";
import { Layout, SoloRoles } from "./components/Layout";
import { Titulo } from "./components/Pieza";
import { Activar, Login } from "./pantallas/Acceso";
import { Comparar } from "./pantallas/Comparar";
import { Distritos } from "./pantallas/Distritos";
import { Ejecuciones } from "./pantallas/Ejecuciones";
import { Ficha } from "./pantallas/Ficha";
import { Inicio } from "./pantallas/Inicio";
import { MiDistrito } from "./pantallas/MiDistrito";
import { Usuarios } from "./pantallas/Usuarios";
import { Versiones } from "./pantallas/Versiones";

function NoEncontrada() {
  return (
    <div className="card vacio">
      <Titulo texto="No encontramos esa página" />
      <h1>No encontramos esa página</h1>
      <p>Puede que el enlace esté mal escrito o que ya no exista.</p>
      <Link className="btn primary" to="/">Ir al inicio</Link>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/activar" element={<Activar />} />
      <Route element={<Layout />}>
        <Route index element={<Inicio />} />
        <Route path="distrito/:ubigeo" element={<MiDistrito />} />
        <Route path="distritos" element={<Distritos />} />
        <Route path="ficha" element={<Ficha />} />
        <Route element={<SoloRoles roles={["analista"]} />}>
          <Route path="comparar" element={<Comparar />} />
          <Route path="ejecuciones" element={<Ejecuciones />} />
        </Route>
        <Route element={<SoloRoles roles={["administrador"]} />}>
          <Route path="versiones" element={<Versiones />} />
          <Route path="usuarios" element={<Usuarios />} />
        </Route>
        <Route path="*" element={<NoEncontrada />} />
      </Route>
    </Routes>
  );
}
