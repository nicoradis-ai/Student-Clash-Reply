# Ereditarietà
Concetto: Ereditarietà
Una classe derivata (`extends`) eredita attributi e metodi della classe base. Si usa per modellare una relazione "è un". Il costruttore della sottoclasse chiama `super(...)`.

---

# Ereditarietà: gerarchie
Concetto: Ereditarietà
Esempio: `Veicolo` → `Auto`, `Moto`. I membri `protected` sono visibili nelle sottoclassi. Evitare gerarchie troppo profonde.

---

# Ereditarietà vs composizione
Concetto: Ereditarietà
Quando la relazione è "ha un", meglio la composizione: un `Auto` ha un `Motore`. Favorire la composizione quando il comportamento può cambiare.

---

# Polimorfismo
Concetto: Polimorfismo
Un riferimento di tipo base può puntare a un oggetto di una sottoclasse. Il metodo eseguito è scelto a runtime (binding dinamico). Override: stessa firma nella sottoclasse; overload: stesso nome, parametri diversi.

---

# Interfacce
Concetto: Interfacce
Un'interfaccia definisce un contratto (`interface Comparable<T>`). Una classe può implementare più interfacce. Metodi `default` dal Java 8.

---

# Interfacce funzionali e lambda
Concetto: Interfacce
Un'interfaccia con un solo metodo astratto si può implementare con una lambda: `list.sort((a, b) -> a.getNome().compareTo(b.getNome()))`.

---

# Eccezioni
Concetto: Eccezioni
Checked (da dichiarare con `throws`) e unchecked (`RuntimeException`). `try / catch / finally`. Creare eccezioni proprie estendendo `Exception`.

---

# Collezioni
Concetto: Collezioni
`List`, `Set`, `Map`. `ArrayList` per accesso per indice, `HashMap` per ricerca per chiave, `TreeMap` per chiavi ordinate.
