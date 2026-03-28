import { useEffect, useState } from "react";

function App() {
  const [message, setMessage] = useState("");

  useEffect(() => {
    fetch("http://localhost:8000/hello")
      .then(response => response.json())
      .then(data => {
        setMessage(data.message);
      })
      .catch(error => {
        console.error("Error:", error);
      });
  }, []);

  return (
    <div>
      <h1>React + FastAPI</h1>
      <p>{message}</p>
    </div>
  );
}

export default App;