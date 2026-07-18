function updateElementStyleProperty(event) {
    event.target.ariaControlsElements.forEach(target => {
        let value = event.target.value
        if (event.target.type === "checkbox") {
            value = event.target.checked
        }
        target.style.setProperty(`--${event.target.name}`, value)
    })
}

function updateElementStyle(event) {
    event.target.ariaControlsElements.forEach(target => {
        let value = event.target.value
        if (event.target.type === "checkbox") { value = event.target.checked }
        target.style.setProperty(event.target.name, value)
    })
}

function updateElementClass(event) {
    if (event.target.type === "checkbox") {
        updateElementCheckbox(event)
    } else {
        updateElementClassSelect(event)
    }
}

function updateElementClassCheckbox(event) {
    event.target.ariaControlsElements.forEach(target => {
        target.classList.toggle(event.target, event.checked)
    })
}
function updateElementClassSelect(event) {
    event.target.ariaControlsElements.forEach(target => {
        Array.from(event.target.options).forEach(option => {
            target.classList.toggle(option.value, option.selected)
        })
    })
}