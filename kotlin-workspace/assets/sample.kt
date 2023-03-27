println("Hello world!")
println("Please wait...")

// Do some work
for (i in 1..100) {
    print(i)
    print(
        if (i % 10 == 0)
        "\n"
        else " "
    )
    Thread.sleep(100)
}

println("See you soon!")
